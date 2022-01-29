import fnmatch
import functools
import json
import numbers
import sys
import threading
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence, SupportsFloat, Tuple, Union

import _frida

_device_manager = None

_Cancellable = _frida.Cancellable

# Mypy doesn't know that int and float inherit from numbers.Number so instead we need to have this hack
ProcessTarget = Union[type[SupportsFloat], type[complex], type[numbers.Number], str]

def get_device_manager() -> core.DeviceManager:
    """
    Get or create a singelton DeviceManager that let you manage all the devices
    """

    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager(_frida.DeviceManager())
    return _device_manager


def _filter_missing_kwargs(d: Dict[str, Any]):
    for key in list(d.keys()):
        if d[key] is None:
            d.pop(key)


def cancellable(f: Callable) -> Callable:
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        cancellable = kwargs.pop("cancellable", None)
        if cancellable is not None:
            with cancellable:
                return f(*args, **kwargs)

        return f(*args, **kwargs)

    return wrapper


class IOStream:
    """
    Frida's own implementation of an input/output stream
    """

    def __init__(self, impl: _frida.IOStream):
        self._impl = impl

    def __repr__(self) -> str:
        return repr(self._impl)

    @property
    def is_closed(self) -> bool:
        """
        Query whether the stream is closed.
        """

        return self._impl.is_closed()

    @cancellable
    def close(self):
        """
        Close the stream.
        """

        self._impl.close()

    @cancellable
    def read(self, count: int) -> bytes:
        """
        Read up to the specified number of bytes from the stream.
        """

        return self._impl.read(count)

    @cancellable
    def read_all(self, count: int) -> bytes:
        """
        Read exactly the specified number of bytes from the stream.
        """

        return self._impl.read_all(count)

    @cancellable
    def write(self, data: bytes):
        """
        Write as much as possible of the provided data to the stream.
        """

        return self._impl.write(data)

    @cancellable
    def write_all(self, data: bytes):
        """
        Write all of the provided data to the stream.
        """

        self._impl.write_all(data)


class PortalMembership:
    def __init__(self, impl: _frida.PortalMembership):
        self._impl = impl

    @cancellable
    def terminate(self):
        """
        Terminate the membership.
        """

        self._impl.terminate()


class ScriptExports:
    """
    Proxy object that expose all the RPC exports of a script as attributes on this class

    A method named exampleMethod in a script will be called with instance.example_method on this object
    """

    def __init__(self, script: "Script"):
        self._script = script

    def __getattr__(self, name: str) -> Any:
        script = self._script
        js_name = _to_camel_case(name)

        def method(*args, **kwargs):
            return script._rpc_request("call", js_name, args, **kwargs)

        return method

    def __dir__(self) -> List[str]:
        return self._script.list_exports()


class Script:
    exports: ScriptExports

    def __init__(self, impl: _frida.Script):
        self.exports = ScriptExports(self)

        self._impl = impl

        self._on_message_callbacks: List[Callable] = []
        self._log_handler: Callable[[str, str], None] = self.default_log_handler

        self._pending: Dict[int, Callable] = {}
        self._next_request_id = 1
        self._cond = threading.Condition()

        impl.on("destroyed", self._on_destroyed)
        impl.on("message", self._on_message)

    def __repr__(self):
        return repr(self._impl)

    @property
    def is_destroyed(self) -> bool:
        """
        Query whether the script has been destroyed.
        """

        return self._impl.is_destroyed()

    @cancellable
    def load(self):
        """
        Load the script.
        """

        self._impl.load()

    @cancellable
    def unload(self):
        """
        Unload the script.
        """

        self._impl.unload()

    @cancellable
    def eternalize(self):
        """
        Eternalize the script.
        """

        self._impl.eternalize()

    def post(self, message: Any, data: Optional[str] = None):
        """
        Post a JSON-encoded message to the script.
        """

        raw_message = json.dumps(message)
        kwargs = {"data": data}
        _filter_missing_kwargs(kwargs)
        self._impl.post(raw_message, **kwargs)

    @cancellable
    def enable_debugger(self, *args, **kwargs):
        self._impl.enable_debugger(*args, **kwargs)

    @cancellable
    def disable_debugger(self):
        self._impl.disable_debugger()

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        if signal == "message":
            self._on_message_callbacks.append(callback)
        else:
            self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        if signal == "message":
            self._on_message_callbacks.remove(callback)
        else:
            self._impl.off(signal, callback)

    def get_log_handler(self) -> Callable[[str, str], None]:
        """
        Get the method that handles the script logs
        """

        return self._log_handler

    def set_log_handler(self, handler: Callable[[str, str], None]):
        """
        Set the method that handles the script logs

        :param handler: a callable that accepts two parameters:
                        1. the log level name
                        2. the log message
        """

        self._log_handler = handler

    def default_log_handler(self, level: str, text: str):
        """
        The default implementation of the log handler, prints the message to stdout
        or stderr, depending on the level
        """

        if level == "info":
            print(text, file=sys.stdout)
        else:
            print(text, file=sys.stderr)

    def list_exports(self) -> List[str]:
        """
        List all the exported attributes from the script's rpc
        """

        return self._rpc_request("list")

    @cancellable
    def _rpc_request(self, *args):
        result = [False, None, None]

        def on_complete(value, error):
            with self._cond:
                result[0] = True
                result[1] = value
                result[2] = error
                self._cond.notify_all()

        def on_cancelled():
            self._pending.pop(request_id, None)
            on_complete(None, None)

        with self._cond:
            request_id = self._next_request_id
            self._next_request_id += 1
            self._pending[request_id] = on_complete

        if not self.is_destroyed:
            message = ["frida:rpc", request_id]
            message.extend(args)
            self.post(message)

            cancellable = Cancellable.get_current()
            cancel_handler = cancellable.connect(on_cancelled)
            try:
                with self._cond:
                    while not result[0]:
                        self._cond.wait()
            finally:
                cancellable.disconnect(cancel_handler)

            cancellable.raise_if_cancelled()
        else:
            self._on_destroyed()

        if result[2] is not None:
            raise result[2]

        return result[1]

    def _on_rpc_message(self, request_id, operation, params, data):
        if operation in ("ok", "error"):
            callback = self._pending.pop(request_id, None)
            if callback is None:
                return

            value = None
            error = None
            if operation == "ok":
                value = params[0] if data is None else data
            else:
                error = RPCException(*params[0:3])

            callback(value, error)

    def _on_destroyed(self):
        while True:
            next_pending = None

            with self._cond:
                pending_ids = list(self._pending.keys())
                if len(pending_ids) > 0:
                    next_pending = self._pending.pop(pending_ids[0])

            if next_pending is None:
                break

            next_pending(None, _frida.InvalidOperationError("script has been destroyed"))

    def _on_message(self, raw_message, data):
        message = json.loads(raw_message)

        mtype = message["type"]
        payload = message.get("payload", None)
        if mtype == "log":
            level = message["level"]
            text = payload
            self._log_handler(level, text)
        elif mtype == "send" and isinstance(payload, list) and len(payload) > 0 and payload[0] == "frida:rpc":
            request_id = payload[1]
            operation = payload[2]
            params = payload[3:]
            self._on_rpc_message(request_id, operation, params, data)
        else:
            for callback in self._on_message_callbacks[:]:
                try:
                    callback(message, data)
                except:
                    traceback.print_exc()


class Session:
    def __init__(self, impl: _frida.Session):
        self._impl = impl

    def __repr__(self) -> str:
        return repr(self._impl)

    @property
    def is_detached(self) -> bool:
        """
        Query whether the session is detached.
        """

        return self._impl.is_detached()

    @cancellable
    def detach(self):
        """
        Detach session from the process.
        """

        self._impl.detach()

    @cancellable
    def resume(self):
        """
        Resume session after network error.
        """

        self._impl.resume()

    @cancellable
    def enable_child_gating(self):
        """
        Enable child gating.
        """

        self._impl.enable_child_gating()

    @cancellable
    def disable_child_gating(self):
        """
        Disable child gating.
        """

        self._impl.disable_child_gating()

    @cancellable
    def create_script(self, source: str, name: Optional[str] = None, runtime: Optional[str] = None) -> Script:
        """
        Create a new script.
        """

        kwargs = {"name": name, "runtime": runtime}
        _filter_missing_kwargs(kwargs)
        return Script(self._impl.create_script(source, **kwargs))

    @cancellable
    def create_script_from_bytes(
        self, data: bytes, name: Optional[str] = None, runtime: Optional[str] = None
    ) -> Script:
        """
        Create a new script from bytecode.
        """

        kwargs = {"name": name, "runtime": runtime}
        _filter_missing_kwargs(kwargs)
        return Script(self._impl.create_script_from_bytes(data, **kwargs))

    @cancellable
    def compile_script(self, source: str, name: Optional[str] = None, runtime: Optional[str] = None) -> bytes:
        """
        Compile script source code to bytecode.
        """

        kwargs = {"name": name, "runtime": runtime}
        _filter_missing_kwargs(kwargs)
        return self._impl.compile_script(source, **kwargs)

    @cancellable
    def snapshot_script(self, *args, **kwargs):
        return self._impl.snapshot_script(*args, **kwargs)

    @cancellable
    def setup_peer_connection(self, stun_server, relays: Sequence[_frida.Relay]):
        """
        Set up a peer connection with the target process.
        """

        kwargs = {"stun_server": stun_server, "relays": relays}
        _filter_missing_kwargs(kwargs)
        self._impl.setup_peer_connection(**kwargs)

    @cancellable
    def join_portal(
        self,
        address: str,
        certificate: Optional[str] = None,
        token: Optional[str] = None,
        acl: Union[List[str], Tuple[str]] = None,
    ) -> PortalMembership:
        """
        Join a portal.
        """

        kwargs: Dict[str, Any] = {"certificate": certificate, "token": token, "acl": acl}
        _filter_missing_kwargs(kwargs)
        return PortalMembership(self._impl.join_portal(address, **kwargs))

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        self._impl.off(signal, callback)


class Bus:
    def __init__(self, impl: _frida.Bus):
        self._impl = impl
        self._on_message_callbacks: List[Callable] = []

        impl.on("message", self._on_message)

    @cancellable
    def attach(self):
        """
        Attach to the bus.
        """

        self._impl.attach()

    def post(self, message: Any, data: Optional[Union[str, bytes]] = None):
        """
        Post a JSON-encoded message to the bus.
        """

        raw_message = json.dumps(message)
        kwargs = {"data": data}
        _filter_missing_kwargs(kwargs)
        self._impl.post(raw_message, **kwargs)

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        if signal == "message":
            self._on_message_callbacks.append(callback)
        else:
            self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        if signal == "message":
            self._on_message_callbacks.remove(callback)
        else:
            self._impl.off(signal, callback)

    def _on_message(self, raw_message, data):
        message = json.loads(raw_message)

        for callback in self._on_message_callbacks[:]:
            try:
                callback(message, data)
            except:
                traceback.print_exc()


class Device:
    """
    Represents a device that Frida connects to
    """

    id: Optional[str]
    name: Optional[str]
    icon: Optional[Any]
    type: Optional[str]
    bus: Optional[Bus]

    def __init__(self, device):
        self.id = device.id
        self.name = device.name
        self.icon = device.icon
        self.type = device.type
        self.bus = Bus(device.bus)

        self._impl = device

    def __repr__(self):
        return repr(self._impl)

    @property
    def is_lost(self) -> bool:
        """
        Query whether the device has been lost.
        """

        return self._impl.is_lost()

    @cancellable
    def query_system_parameters(self) -> Dict[str, Any]:
        """
        Returns a dictionary of information about the host system.
        """

        return self._impl.query_system_parameters()

    @cancellable
    def get_frontmost_application(self, scope: Optional[str] = None) -> Optional[_frida.Application]:
        """
        Get details about the frontmost application.
        """

        kwargs = {"scope": scope}
        _filter_missing_kwargs(kwargs)
        return self._impl.get_frontmost_application(**kwargs)

    @cancellable
    def enumerate_applications(
        self, identifiers: Optional[Sequence[str]] = None, scope: Optional[str] = None
    ) -> List[_frida.Application]:
        """
        Enumerate applications.
        """

        kwargs = {"identifiers": identifiers, "scope": scope}
        _filter_missing_kwargs(kwargs)
        return self._impl.enumerate_applications(**kwargs)

    @cancellable
    def enumerate_processes(
        self, pids: Optional[Sequence[int]] = None, scope: Optional[str] = None
    ) -> List[_frida.Process]:
        """
        Enumerate processes.
        """

        kwargs = {"pids": pids, "scope": scope}
        _filter_missing_kwargs(kwargs)
        return self._impl.enumerate_processes(**kwargs)

    @cancellable
    def get_process(self, process_name: str) -> _frida.Process:
        """
        Get the process with the given name

        :raises ProcessNotFoundError: if the process was not found or there were more than one process with the given name
        """

        process_name_lc = process_name.lower()
        matching = [
            process
            for process in self._impl.enumerate_processes()
            if fnmatch.fnmatchcase(process.name.lower(), process_name_lc)
        ]
        if len(matching) == 1:
            return matching[0]
        elif len(matching) > 1:
            matches_list = ", ".join([f"{process.name} (pid: {process.pid})" for process in matching])
            raise _frida.ProcessNotFoundError(f"ambiguous name; it matches: {matches_list}")
        else:
            raise _frida.ProcessNotFoundError(f"unable to find process with name '{process_name}'")

    @cancellable
    def enable_spawn_gating(self):
        """
        Enable spawn gating.
        """

        self._impl.enable_spawn_gating()

    @cancellable
    def disable_spawn_gating(self):
        """
        Disable spawn gating.
        """

        self._impl.disable_spawn_gating()

    @cancellable
    def enumerate_pending_spawn(self) -> List[_frida.Spawn]:
        """
        Enumerate pending spawn.
        """

        return self._impl.enumerate_pending_spawn()

    @cancellable
    def enumerate_pending_children(self) -> List[_frida.Child]:
        """
        Enumerate pending children.
        """

        return self._impl.enumerate_pending_children()

    @cancellable
    def spawn(
        self,
        program: Union[str, List, Tuple],
        argv: Optional[Union[List, Tuple]] = None,
        envp: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdio: Optional[str] = None,
        **kwargs,
    ) -> int:
        """
        Spawn a process into an attachable state.
        """

        if not isinstance(program, str):
            argv = program
            program = argv[0]
            if len(argv) == 1:
                argv = None

        kwargs = {"argv": argv, "envp": envp, "env": env, "cwd": cwd, "stdio": stdio, "aux": kwargs}
        _filter_missing_kwargs(kwargs)
        return self._impl.spawn(program, **kwargs)

    @cancellable
    def input(self, target: ProcessTarget, data: bytes):
        """
        Input data on stdin of a spawned process.

        :params target: the PID or name of the process
        """

        self._impl.input(self._pid_of(target), data)

    @cancellable
    def resume(self, target: ProcessTarget):
        """
        Resume a process from the attachable state.

        :params target: the PID or name of the process
        """

        self._impl.resume(self._pid_of(target))

    @cancellable
    def kill(self, target: ProcessTarget):
        """
        Kill a process.

        :params target: the PID or name of the process
        """

        self._impl.kill(self._pid_of(target))

    @cancellable
    def attach(
        self,
        target: ProcessTarget,
        realm: Optional[str] = None,
        persist_timeout: Optional[int] = None,
    ) -> Session:
        """
        Attach to a process.

        :params target: the PID or name of the process
        """

        kwargs = {"realm": realm, "persist_timeout": persist_timeout}
        _filter_missing_kwargs(kwargs)
        return Session(self._impl.attach(self._pid_of(target), **kwargs))

    @cancellable
    def inject_library_file(self, target: ProcessTarget, path: str, entrypoint: str, data: str) -> int:
        """
        Inject a library file to a process.

        :params target: the PID or name of the process
        """

        return self._impl.inject_library_file(self._pid_of(target), path, entrypoint, data)

    @cancellable
    def inject_library_blob(self, target: ProcessTarget, blob: bytes, entrypoint: str, data: str) -> int:
        """
        Inject a library blob to a process.

        :params target: the PID or name of the process
        """

        return self._impl.inject_library_blob(self._pid_of(target), blob, entrypoint, data)

    @cancellable
    def open_channel(self, address: str) -> IOStream:
        """
        Open a device-specific communication channel.
        """

        return IOStream(self._impl.open_channel(address))

    @cancellable
    def get_bus(self) -> Bus:
        """
        Get the message bus of the device
        """

        return Bus(self._impl.get_bus())

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        self._impl.off(signal, callback)

    def _pid_of(self, target: ProcessTarget) -> int:
        if isinstance(target, numbers.Number):
            return target
        else:
            return self.get_process(target).pid


class DeviceManager:
    def __init__(self, impl: _frida.DeviceManager):
        self._impl = impl

    def __repr__(self) -> str:
        return repr(self._impl)

    def get_local_device(self) -> Device:
        """
        Get the local device
        """

        return self.get_device_matching(lambda d: d.type == "local", timeout=0)

    def get_remote_device(self) -> Device:
        """
        Get the first remote device in the devices list
        """

        return self.get_device_matching(lambda d: d.type == "remote", timeout=0)

    def get_usb_device(self, timeout: int = 0) -> Device:
        """
        Get the first device connected over USB in the devices list
        """

        return self.get_device_matching(lambda d: d.type == "usb", timeout)

    def get_device(self, id: Optional[str], timeout: int = 0) -> Device:
        """
        Get a device by its id
        """

        return self.get_device_matching(lambda d: d.id == id, timeout)

    @cancellable
    def get_device_matching(self, predicate: Callable[[Device], bool], timeout: int = 0) -> Device:
        """
        Get device matching predicate.

        :params predicate: a function to filter the devices
        :params timeout: operation timeout in seconds
        """

        if timeout < 0:
            raw_timeout = -1
        elif timeout == 0:
            raw_timeout = 0
        else:
            raw_timeout = int(timeout * 1000.0)
        return Device(self._impl.get_device_matching(lambda d: predicate(Device(d)), raw_timeout))

    @cancellable
    def enumerate_devices(self) -> List[Device]:
        """
        Enumerate devices.
        """

        return [Device(device) for device in self._impl.enumerate_devices()]

    @cancellable
    def add_remote_device(
        self,
        address: str,
        certificate: Optional[str] = None,
        origin: Optional[str] = None,
        token: Optional[str] = None,
        keepalive_interval: Optional[int] = None,
    ) -> Device:
        """
        Add a remote device.
        """

        kwargs: Dict[str, Any] = {
            "certificate": certificate,
            "origin": origin,
            "token": token,
            "keepalive_interval": keepalive_interval,
        }
        _filter_missing_kwargs(kwargs)
        return Device(self._impl.add_remote_device(address, **kwargs))

    @cancellable
    def remove_remote_device(self, address: str):
        """
        Remove a remote device.
        """

        self._impl.remove_remote_device(address=address)

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        self._impl.off(signal, callback)


class RPCException(Exception):
    """
    Wraps remote errors from the script RPC
    """

    def __str__(self) -> str:
        return self.args[2] if len(self.args) >= 3 else self.args[0]


class EndpointParameters:
    def __init__(
        self,
        address: Optional[str] = None,
        port: Optional[int] = None,
        certificate: Optional[str] = None,
        origin: Optional[str] = None,
        authentication: Optional[Tuple[str, Union[str, Callable[[str], Any]]]] = None,
        asset_root: Optional[str] = None,
    ):
        kwargs: Dict[str, Any] = {"address": address, "port": port, "certificate": certificate}
        if asset_root is not None:
            kwargs["asset_root"] = str(asset_root)
        _filter_missing_kwargs(kwargs)

        if authentication is not None:
            (auth_scheme, auth_data) = authentication
            if auth_scheme == "token":
                kwargs["auth_token"] = auth_data
            elif auth_scheme == "callback":
                if not callable(auth_data):
                    raise ValueError(
                        "Authentication data must provide a Callable if the authentication scheme is callback"
                    )
                kwargs["auth_callback"] = make_auth_callback(auth_data)
            else:
                raise ValueError("invalid authentication scheme")

        self._impl = _frida.EndpointParameters(**kwargs)


class PortalService:
    def __init__(
        self,
        cluster_params: EndpointParameters = EndpointParameters(),
        control_params: Optional[EndpointParameters] = None,
    ):
        args = [cluster_params._impl]
        if control_params is not None:
            args.append(control_params._impl)
        impl = _frida.PortalService(*args)

        self.device = impl.device
        self._impl = impl
        self._on_authenticated_callbacks: List[Callable] = []
        self._on_message_callbacks: List[Callable] = []

        impl.on("authenticated", self._on_authenticated)
        impl.on("message", self._on_message)

    @cancellable
    def start(self):
        """
        Start listening for incoming connections.

        :raises InvalidOperationError: if the service isn't stopped
        :raises AddressInUseError: if the given address is already in use
        """

        self._impl.start()

    @cancellable
    def stop(self):
        """
        Stop listening for incoming connections, and kick any connected clients.

        :raises InvalidOperationError: if the service is already stopped
        """

        self._impl.stop()

    def post(self, connection_id: int, message: Any, data: Optional[Union[str, bytes]] = None):
        """
        Post a message to a specific control channel.
        """

        raw_message = json.dumps(message)
        kwargs = {"data": data}
        _filter_missing_kwargs(kwargs)
        self._impl.post(connection_id, raw_message, **kwargs)

    def narrowcast(self, tag: str, message: Any, data: Optional[Union[str, bytes]] = None):
        """
        Post a message to control channels with a specific tag.
        """

        raw_message = json.dumps(message)
        kwargs = {"data": data}
        _filter_missing_kwargs(kwargs)
        self._impl.narrowcast(tag, raw_message, **kwargs)

    def broadcast(self, message: Any, data: Optional[Union[str, bytes]] = None):
        """
        Broadcast a message to all control channels.
        """

        raw_message = json.dumps(message)
        kwargs = {"data": data}
        _filter_missing_kwargs(kwargs)
        self._impl.broadcast(raw_message, **kwargs)

    def enumerate_tags(self, connection_id: int) -> List[str]:
        """
        Enumerate tags of a specific connection.
        """

        return self._impl.enumerate_tags(connection_id)

    def tag(self, connection_id: int, tag: str):
        """
        Tag a specific control channel.
        """

        self._impl.tag(connection_id, tag)

    def untag(self, connection_id: int, tag: str):
        """
        Untag a specific control channel.
        """

        self._impl.untag(connection_id, tag)

    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """

        if signal == "authenticated":
            self._on_authenticated_callbacks.append(callback)
        elif signal == "message":
            self._on_message_callbacks.append(callback)
        else:
            self._impl.on(signal, callback)

    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """

        if signal == "authenticated":
            self._on_authenticated_callbacks.remove(callback)
        elif signal == "message":
            self._on_message_callbacks.remove(callback)
        else:
            self._impl.off(signal, callback)

    def _on_authenticated(self, connection_id: int, raw_session_info: str):
        session_info = json.loads(raw_session_info)

        for callback in self._on_authenticated_callbacks[:]:
            try:
                callback(connection_id, session_info)
            except:
                traceback.print_exc()

    def _on_message(self, connection_id: int, raw_message: str, data: Any):
        message = json.loads(raw_message)

        for callback in self._on_message_callbacks[:]:
            try:
                callback(connection_id, message, data)
            except:
                traceback.print_exc()


class Compiler(object):
    def __init__(self):
        self._impl = _frida.Compiler(get_device_manager()._impl)

    def __repr__(self):
        return repr(self._impl)

    @cancellable
    def build(self, *args, **kwargs):
        return self._impl.build(*args, **kwargs)

    @cancellable
    def watch(self, *args, **kwargs):
        return self._impl.watch(*args, **kwargs)

    def on(self, signal, callback):
        self._impl.on(signal, callback)

    def off(self, signal, callback):
        self._impl.off(signal, callback)


class IOStream:
    def __init__(self, impl):
        self._impl = impl

    def __repr__(self):
        return repr(self._impl)

    @property
    def is_closed(self):
        return self._impl.is_closed()

    @cancellable
    def close(self):
        self._impl.close()

    @cancellable
    def read(self, count):
        return self._impl.read(count)

    @cancellable
    def read_all(self, count):
        return self._impl.read_all(count)

    @cancellable
    def write(self, data):
        return self._impl.write(data)

    @cancellable
    def write_all(self, data):
        self._impl.write_all(data)


class Cancellable:
    def __init__(self):
        self._impl = _Cancellable()

    def __repr__(self):
        return repr(self._impl)

    @property
    def is_cancelled(self):
        return self._impl.is_cancelled()

    def raise_if_cancelled(self):
        self._impl.raise_if_cancelled()

    def get_pollfd(self):
        return CancellablePollFD(self._impl)

    @classmethod
    def get_current(cls):
        return _Cancellable.get_current()

    def __enter__(self):
        self._impl.push_current()

    def __exit__(self, *args):
        self._impl.pop_current()

    def connect(self, callback):
        return self._impl.connect(callback)

    def disconnect(self, handler_id):
        self._impl.disconnect(handler_id)

    def cancel(self):
        self._impl.cancel()


class CancellablePollFD:
    def __init__(self, cancellable):
        self.handle = cancellable.get_fd()
        self._cancellable = cancellable

    def __del__(self):
        self.release()

    def release(self):
        if self._cancellable is not None:
            if self.handle != -1:
                self._cancellable.release_fd()
                self.handle = -1
            self._cancellable = None

    def __repr__(self) -> str:
        return repr(self.handle)

    def __enter__(self) -> int:
        return self.handle

    def __exit__(self, *args):
        self.release()


class Cancellable:
    def __init__(self):
        self._impl = _Cancellable()

    def __repr__(self) -> str:
        return repr(self._impl)

    @property
    def is_cancelled(self) -> bool:
        """
        Query whether cancellable has been cancelled.
        """

        return self._impl.is_cancelled()

    def raise_if_cancelled(self):
        """
        Raise an exception if cancelled.

        :raises OperationCancelledError:
        """

        self._impl.raise_if_cancelled()

    def get_pollfd(self) -> CancellablePollFD:
        return CancellablePollFD(self._impl)

    @classmethod
    def get_current(cls) -> _frida.Cancellable:
        """
        Get the top cancellable from the stack.
        """

        return _Cancellable.get_current()

    def __enter__(self):
        self._impl.push_current()

    def __exit__(self, *args):
        self._impl.pop_current()

    def connect(self, callback: Callable) -> int:
        """
        Register notification callback.

        :returns: the created handler id
        """

        return self._impl.connect(callback)

    def disconnect(self, handler_id: int):
        """
        Unregister notification callback.
        """

        self._impl.disconnect(handler_id)

    def cancel(self):
        """
        Set cancellable to cancelled.
        """

        self._impl.cancel()


def make_auth_callback(callback: Callable) -> Callable[[Any], str]:
    """
    Wraps authenticated callbacks with JSON marshaling
    """

    def authenticate(token):
        session_info = callback(token)
        return json.dumps(session_info)

    return authenticate


def _to_camel_case(name: str) -> str:
    result = ""
    uppercase_next = False
    for c in name:
        if c == "_":
            uppercase_next = True
        elif uppercase_next:
            result += c.upper()
            uppercase_next = False
        else:
            result += c.lower()
    return result

from typing import Any, Callable, ClassVar, Dict, List, Optional, Sequence, Tuple, Union

# Exceptions
class AddressInUseError(Exception): ...
class ExecutableNotFoundError(Exception): ...
class ExecutableNotSupportedError(Exception): ...
class ServerNotRunningError(Exception): ...
class TimedOutError(Exception): ...
class TransportError(Exception): ...
class ProcessNotFoundError(Exception): ...
class ProcessNotRespondingError(Exception): ...
class ProtocolError(Exception): ...
class InvalidArgumentError(Exception): ...
class InvalidOperationError(Exception): ...
class NotSupportedError(Exception): ...
class OperationCancelledError(Exception): ...
class PermissionDeniedError(Exception): ...

class Object:
    def on(self, signal: str, callback: Callable):
        """
        Add a signal handler.
        """
        ...
    def off(self, signal: str, callback: Callable):
        """
        Remove a signal handler.
        """
        ...

class Application(Object):
    def __init__(self, *args, **kwargs) -> None: ...
    @property
    def identifier(self) -> str:
        """
        Application identifier.
        """
        ...
    @property
    def name(self) -> str:
        """
        Human-readable application name.
        """
        ...
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        Parameters.
        """
        ...
    @property
    def pid(self) -> int:
        """
        Process ID, or 0 if not running.
        """
        ...

class Bus(Object):
    def attach(self):
        """
        Attach to the bus.
        """
        ...
    def post(self, message: str, data: Optional[Union[bytes, str]]) -> Any:
        """
        Post a JSON-encoded message to the bus.
        """
        ...

class Cancellable(Object):
    def cancel(self):
        """
        Set cancellable to cancelled.
        """
        ...
    def connect(self, callback: Callable) -> int:
        """
        Register notification callback.
        """
        ...
    def disconnect(self, handler_id: int):
        """
        Unregister notification callback.
        """
        ...
    @classmethod
    def get_current(cls) -> "Cancellable":
        """
        Get the top cancellable from the stack.
        """
        ...
    def get_fd(self) -> int:
        """
        Get file descriptor for integrating with an event loop.
        """
        ...
    def is_cancelled(self) -> bool:
        """
        Query whether cancellable has been cancelled.
        """
        ...
    def pop_current(self):
        """
        Pop cancellable off the cancellable stack.
        """
        ...
    def push_current(self):
        """
        Push cancellable onto the cancellable stack.
        """
        ...
    def raise_if_cancelled(self):
        """
        Raise an exception if cancelled.
        """
        ...
    def release_fd(self):
        """
        Release a resource previously allocated by get_fd().
        """
        ...

class Child(Object):
    @property
    def argv(self) -> List[str]:
        """
        Argument vector.
        """
        ...
    @property
    def envp(self) -> Dict[str, str]:
        """
        Environment vector.
        """
        ...
    @property
    def identifier(self) -> str:
        """
        Application identifier.
        """
        ...
    @property
    def origin(self) -> str:
        """
        Origin.
        """
        ...
    @property
    def parent_pid(self) -> int:
        """
        Parent Process ID.
        """
        ...
    @property
    def path(self) -> str:
        """
        Path of executable.
        """
        ...
    @property
    def pid(self) -> int:
        """
        Process ID.
        """
        ...

class Crash(Object):
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        Parameters.
        """
        ...
    @property
    def pid(self) -> int:
        """
        Process ID.
        """
        ...
    @property
    def process_name(self) -> str:
        """
        Process name.
        """
        ...
    @property
    def report(self) -> str:
        """
        Human-readable crash report.
        """
        ...
    @property
    def summary(self) -> str:
        """
        Human-readable crash summary.
        """
        ...

class Device(Object):
    @property
    def id(self) -> Optional[str]:
        """
        Device ID.
        """
        ...
    @property
    def name(self) -> Optional[str]:
        """
        Human-readable device name.
        """
        ...
    @property
    def icon(self) -> Optional[Any]:
        """
        Icon.
        """
        ...
    @property
    def type(self) -> Optional[str]:
        """
        Device type. One of: local, remote, usb.
        """
        ...
    @property
    def bus(self) -> Optional[Bus]:
        """
        Message bus.
        """
        ...
    def attach(self, pid: int, realm: Optional[str] = None, persist_timeout: Optional[int] = None) -> "Session":
        """
        Attach to a PID.
        """
        ...
    def disable_spawn_gating(self):
        """
        Disable spawn gating.
        """
        ...
    def enable_spawn_gating(self):
        """
        Enable spawn gating.
        """
        ...
    def enumerate_applications(self, identifiers: Optional[Sequence[str]] = None, scope: Optional[str] = None) -> Any:
        """
        Enumerate applications.
        """
        ...
    def enumerate_pending_children(self) -> List[Child]:
        """
        Enumerate pending children.
        """
        ...
    def enumerate_pending_spawn(self) -> List["Spawn"]:
        """
        Enumerate pending spawn.
        """
        ...
    def enumerate_processes(self, pids: Optional[Sequence[int]] = None, scope: Optional[str] = None) -> Any:
        """
        Enumerate processes.
        """
        ...
    def get_frontmost_application(self, scope: Optional[str] = None) -> Optional[Application]:
        """
        Get details about the frontmost application.
        """
        ...
    def inject_library_blob(self, pid: int, blob_buffer: bytes, entrypoint: str, data: str) -> int:
        """
        Inject a library blob to a PID.
        """
        ...
    def inject_library_file(self, pid: int, path: str, entrypoint: str, data: str) -> int:
        """
        Inject a library file to a PID.
        """
        ...
    def input(self, pid: int, data: bytes):
        """
        Input data on stdin of a spawned process.
        """
        ...
    def is_lost(self) -> bool:
        """
        Query whether the device has been lost.
        """
        ...
    def kill(self, pid: int):
        """
        Kill a PID.
        """
        ...
    def open_channel(self, address: str) -> "IOStream":
        """
        Open a device-specific communication channel.
        """
        ...
    def query_system_parameters(self) -> Dict[str, Any]:
        """
        Returns a dictionary of information about the host system.
        """
        ...
    def resume(self, pid: int):
        """
        Resume a process from the attachable state.
        """
        ...
    def spawn(
        self,
        program: str,
        argv: Optional[Union[List[Union[str, bytes]], Tuple[Union[str, bytes]]]] = None,
        envp: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdio: Optional[str] = None,
        **kwargs,
    ) -> int:
        """
        Spawn a process into an attachable state.
        """
        ...

class DeviceManager(Object):
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
        ...
    def close(self):
        """
        Close the device manager.
        """
        ...
    def enumerate_devices(self) -> List[Device]:
        """
        Enumerate devices.
        """
        ...
    def get_device_matching(self, predicate: Callable[[Device], bool], timeout: int) -> Device:
        """
        Get device matching predicate.
        """
        ...
    def remove_remote_device(self, address: str):
        """
        Remove a remote device.
        """
        ...

class EndpointParameters(Object): ...

class FileMonitor(Object):
    def disable(self):
        """
        Disable the file monitor.
        """
        ...
    def enable(self):
        """
        Enable the file monitor.
        """
        ...

class IOStream(Object):
    def close(self):
        """
        Close the stream.
        """
        ...
    def is_closed(self) -> bool:
        """
        Query whether the stream is closed.
        """
        ...
    def read(self, size: int) -> bytes:
        """
        Read up to the specified number of bytes from the stream.
        """
        ...
    def read_all(self, size: int) -> bytes:
        """
        Read exactly the specified number of bytes from the stream.
        """
        ...
    def write(self, data: bytes) -> int:
        """
        Write as much as possible of the provided data to the stream.
        """
        ...
    def write_all(self, data: bytes):
        """
        Write all of the provided data to the stream.
        """
        ...

class PortalMembership(Object):
    def terminate(self):
        """
        Terminate the membership.
        """
        ...

class PortalService(Object):
    @property
    def device(self) -> Device:
        """
        Device for in-process control.
        """
        ...
    def broadcast(self, message: str, data: Optional[Union[str, bytes]] = None):
        """
        Broadcast a message to all control channels.
        """
        ...
    def enumerate_tags(self, connection_id: int) -> List[str]:
        """
        Enumerate tags of a specific connection.
        """
        ...
    def kick(self, connection_id: int):
        """
        Kick out a specific connection.
        """
        ...
    def narrowcast(self, tag: str, message: str, data: Optional[Union[str, bytes]] = None):
        """
        Post a message to control channels with a specific tag.
        """
        ...
    def post(self, connection_id: int, message: str, data: Optional[Union[str, bytes]] = None):
        """
        Post a message to a specific control channel.
        """
        ...
    def start(self):
        """
        Start listening for incoming connections.
        """
        ...
    def stop(self):
        """
        Stop listening for incoming connections, and kick any connected clients.
        """
        ...
    def tag(self, connection_id: int, tag: str):
        """
        Tag a specific control channel.
        """
        ...
    def untag(self, connection_id: int, tag: str):
        """
        Untag a specific control channel.
        """
        ...

class Process(Object):
    @property
    def pid(self) -> int:
        """
        Process ID.
        """
        ...
    @property
    def name(self) -> str:
        """
        Human-readable process name.
        """
        ...
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        Parameters.
        """
        ...

class Relay(Object):
    def __init__(self, address: str, username: str, password: str, kind: str): ...
    @property
    def address(self) -> str:
        """
        Network address or address:port of the TURN server.
        """
        ...
    @property
    def kind(self) -> str:
        """
        Relay kind. One of: turn-udp, turn-tcp, turn-tls.
        """
        ...
    @property
    def password(self) -> str:
        """
        The TURN password to use for the allocate request.
        """
        ...
    @property
    def username(self) -> str:
        """
        The TURN username to use for the allocate request.
        """
        ...

class Script(Object):
    def eternalize(self):
        """
        Eternalize the script.
        """
        ...
    def is_destroyed(self) -> bool:
        """
        Query whether the script has been destroyed.
        """
        ...
    def load(self):
        """
        Load the script.
        """
        ...
    def post(self, message: str, data: Optional[Union[str, bytes]] = None) -> Any:
        """
        Post a JSON-encoded message to the script.
        """
        ...
    def unload(self):
        """
        Unload the script.
        """
        ...

class Session(Object):
    @property
    def pid(self) -> int:
        """
        Process ID.
        """
        ...
    def compile_script(self, source: str, name: Optional[str] = None, runtime: Optional[str] = None) -> bytes:
        """
        Compile script source code to bytecode.
        """
        ...
    def create_script(self, source: str, name: Optional[str] = None, runtime: Optional[str] = None) -> Script:
        """
        Create a new script.
        """
        ...
    def create_script_from_bytes(
        self, data: bytes, name: Optional[str] = None, runtime: Optional[str] = None
    ) -> Script:
        """
        Create a new script from bytecode.
        """
        ...
    def detach(self):
        """
        Detach session from the process.
        """
        ...
    def disable_child_gating(self):
        """
        Disable child gating.
        """
        ...
    def disable_debugger(self):
        """
        Disable the Node.js compatible script debugger.
        """
        ...
    def enable_child_gating(self):
        """
        Enable child gating.
        """
        ...
    def enable_debugger(self, port: Optional[int] = None):
        """
        Enable the Node.js compatible script debugger.
        """
        ...
    def is_detached(self) -> bool:
        """
        Query whether the session is detached.
        """
        ...
    def join_portal(
        self, address: str, certificate: Optional[str] = None, token: Optional[str] = None, acl: Optional[Any] = None
    ) -> PortalMembership:
        """
        Join a portal.
        """
        ...
    def resume(self):
        """
        Resume session after network error.
        """
        ...
    def setup_peer_connection(self, stun_server: Optional[str] = None, relays: Optional[Sequence[Relay]] = None) -> Any:
        """
        Set up a peer connection with the target process.
        """
        ...

class Spawn(Object):
    def __init__(self, *args, **kwargs) -> None: ...
    @property
    def identifier(self) -> str:
        """
        Application identifier.
        """
        ...
    @property
    def pid(self) -> int:
        """
        Process ID.
        """
        ...

__version__: str

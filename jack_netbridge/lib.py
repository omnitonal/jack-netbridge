# base_daemon.py
from abc import ABC, abstractmethod
import socket
import struct
import fcntl

import threading
import queue
import time

import jack
import mido
import numpy as np

DEFAULT_MULTICAST_TTL = 2
DEFAULT_MULTICAST_PORT = 4000
DEFAULT_BUFFER_SIZE = 1024


class NetworkingSettingsHandler:

    @staticmethod
    def get_ip_address_by_interface_name(ifname):
        """Resolve an interface's name to its IP address.

        Example: eth0 -> 192.168.0.1
        """

        # Create a new socket for IPv4 communication using the UDP protocol
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            # Get the file descriptor for the socket
            fileno = s.fileno()

            # Prepare the data structure for the ioctl call;
            # Truncate/pad the interface name to 15 bytes and encode it
            packed_ifname = struct.pack('256s', ifname[:15].encode('utf-8'))

            # Perform the ioctl call to get the IP address associated with the interface
            # SIOCGIFADDR (0x8915) is the command to get the address
            ioctl_result = fcntl.ioctl(fileno, 0x8915, packed_ifname)

            # Extract the IP address bytes from the result
            ip_bytes = ioctl_result[20:24]

            # Convert the IP address bytes to string representation
            ip_address = socket.inet_ntoa(ip_bytes)

            return ip_address

        except IOError:
            # Handle any IO exceptions (like interface not found)
            return None


class BaseJackNetworkBridge(ABC):

    def __init__(self, jack_client_name, jack_port_name: str):
        self.jack_port_name = jack_port_name
        self.jack_client_name = jack_client_name
        self.stop_event = None

    def start(self):
        with self.client:
            print("JACK client activated:", self.jack_client_name)
            while True:
                time.sleep(1)
                if self.stop_event.is_set():
                    break

class BaseReceiver(BaseJackNetworkBridge):

    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0
                 ):
        super().__init__(jack_client_name, jack_port_name)
        self.multicast_group = multicast_group
        self.interface_ip = NetworkingSettingsHandler.get_ip_address_by_interface_name(interface_name)
        self.multicast_ttl = multicast_ttl
        self.multicast_port = multicast_port
        self.buffer_size = buffer_size
        self.queue = queue.Queue()
        self.setup_multicast_socket()
        self.listener_thread = threading.Thread(target=self.listen_multicast)

    def setup_multicast_socket(self):
        # Create a UDP socket for IPv4 communication
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Allow multiple sockets to use the same PORT number
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind the socket to the specified multicast group IP and port
        self.sock.bind((self.multicast_group, self.multicast_port))

        # Pack the multicast group IP and INADDR_ANY constant into a binary data structure
        mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)

        # Add the socket to the multicast group
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Set a timeout on blocking socket operations (in seconds)
        self.sock.settimeout(1)

    @abstractmethod
    def listen_multicast(self):
        raise NotImplemented("This method must be implemented in a subclass!")


class BaseTransmitter(BaseJackNetworkBridge):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0):
        super().__init__(jack_client_name, jack_port_name)
        self.multicast_group = multicast_group
        self.interface_ip = NetworkingSettingsHandler.get_ip_address_by_interface_name(interface_name)
        self.multicast_ttl = multicast_ttl
        self.multicast_port = multicast_port
        self.buffer_size = buffer_size
        if self.buffer_size == 0:
            self.buffer_size = 1024
        self.buffer = bytearray()
        self.setup_multicast_socket()

    def setup_multicast_socket(self):
        # Create a new UDP socket for IPv4 communication
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Allow the socket to reuse the address, useful in multicast to avoid the 'Address already in use' error
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Set the time-to-live (TTL) for multicast. This determines how many network hops the packet will take before being discarded
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', self.multicast_ttl))

        # Bind the socket to the specific interface IP address and an ephemeral port (port 0 lets the OS choose an available port)
        self.sock.bind((self.interface_ip, 0))

    def send_multicast(self, data: bytes):
        self.sock.sendto(data, (self.multicast_group, self.multicast_port))

class MidiReceiver(BaseReceiver):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = None
                 ) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_name, multicast_ttl, multicast_port, buffer_size)

        self.midi_queue = queue.Queue()
        self.setup_jack()

        self.listener_thread.start()

    def setup_jack(self) -> None:
        self.client = jack.Client(self.jack_client_name)

        if not self.client:
            raise RuntimeError("Failed to create JACK client.")

        self.buffer_size = self.client.blocksize
        self.port_handle = self.client.midi_outports.register(self.jack_port_name)

        self.client.set_process_callback(self.process_callback)

    def process_callback(self, frames: int) -> None:
        self.port_handle.clear_buffer()
        while not self.midi_queue.empty():
            midi_data = self.midi_queue.get_nowait()
            msg = mido.parse_all(midi_data)
            for m in msg:
                self.port_handle.write_midi_event(0, m.bytes())


    def listen_multicast(self) -> None:
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                break
            try:
                data, addr = self.sock.recvfrom(64)
                self.midi_queue.put(data)
            except Exception as e:
                pass


class MidiTransmitter(BaseTransmitter):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = None
                 ) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_name, multicast_ttl, multicast_port, buffer_size)

        self.setup_jack()

    def setup_jack(self) -> None:
        self.client = jack.Client(self.jack_client_name)

        if not self.client:
            raise RuntimeError("Failed to create JACK client.")

        self.buffer_size = self.client.blocksize
        self.port_handle = self.client.midi_inports.register(self.jack_port_name)
        self.client.set_process_callback(self.process_callback)

    def process_callback(self, frames: int) -> None:
        for offset, data in self.port_handle.incoming_midi_events():
            self.send_multicast(data)

class AudioReceiver(BaseReceiver):

    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_name, multicast_ttl, multicast_port, buffer_size)

        self.setup_jack()
        self.listener_thread.start()

    def setup_jack(self) -> None:
        self.client = jack.Client(self.jack_client_name)
        if not self.client:
            raise RuntimeError("Failed to create JACK client.")

        self.buffer_size = self.client.blocksize
        self.output_port = self.client.outports.register(self.jack_port_name)

        self.client.set_process_callback(self.process_callback)

    def process_callback(self, frames: int) -> None:
        if not self.queue.empty():
            audio_data = self.queue.get_nowait()
            self.output_port.get_buffer()[:] = np.fromstring(audio_data, dtype=np.float32)

    def listen_multicast(self) -> None:
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                break
            try:
                data, addr = self.sock.recvfrom(self.buffer_size * 4) # 4 because of float32
                self.queue.put(data)
            except Exception as e:
                pass

class AudioTransmitter(BaseTransmitter):

    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_name: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_name, multicast_ttl, multicast_port, buffer_size)
        self.setup_jack()

    def setup_jack(self) -> None:
        self.client = jack.Client(self.jack_client_name)
        if not self.client:
            raise RuntimeError("Failed to create JACK client.")

        self.buffer_size = self.client.blocksize
        self.input_port = self.client.inports.register(self.jack_port_name)
        self.client.set_process_callback(self.process_callback)

    def process_callback(self, frames: int) -> None:
        self.buffer.extend(self.input_port.get_array().tobytes())
        if len(self.buffer) >= self.buffer_size:
            self.send_multicast(self.buffer)
            self.buffer.clear()

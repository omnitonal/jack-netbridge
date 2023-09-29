#!/usr/bin/env python3
"""
A script to forward incoming MIDI events from JACK to a multicast group and vice versa.
"""
# base_daemon.py
from abc import ABC, abstractmethod
import socket
import struct
import threading
import queue
import argparse
import time

import jack
import mido
import numpy as np

DEFAULT_MULTICAST_TTL = 2
DEFAULT_MULTICAST_PORT = 4000
DEFAULT_BUFFER_SIZE = 1024

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
                 interface_ip: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0
                 ):
        super().__init__(jack_client_name, jack_port_name)
        self.multicast_group = multicast_group
        self.interface_ip = interface_ip
        self.multicast_ttl = multicast_ttl
        self.multicast_port = multicast_port
        self.buffer_size = buffer_size
        self.queue = queue.Queue()
        self.setup_multicast_socket()
        self.listener_thread = threading.Thread(target=self.listen_multicast)

    def setup_multicast_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.multicast_group, self.multicast_port))
        mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.sock.settimeout(1)


    @abstractmethod
    def listen_multicast(self):
        raise NotImplemented("This method must be implemented in a subclass!")


class BaseTransmitter(BaseJackNetworkBridge):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_ip: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = 0):
        super().__init__(jack_client_name, jack_port_name)
        self.multicast_group = multicast_group
        self.interface_ip = interface_ip
        self.multicast_ttl = multicast_ttl
        self.multicast_port = multicast_port
        self.buffer_size = buffer_size
        if self.buffer_size == 0:
            self.buffer_size = 1024
        self.buffer = bytearray()
        self.setup_multicast_socket()

    def setup_multicast_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', self.multicast_ttl))
        self.sock.bind((self.interface_ip, 0))

    def send_multicast(self, data: bytes):
        self.sock.sendto(data, (self.multicast_group, self.multicast_port))

class MidiReceiver(BaseReceiver):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_ip: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = None
                 ) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_ip, multicast_ttl, multicast_port, buffer_size)

        self.midi_queue = queue.Queue()
        self.setup_jack()

        print("Launching listener thread")
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
                print("Parsed", msg)
                self.port_handle.write_midi_event(0, m.bytes())


    def listen_multicast(self) -> None:
        print("listener thread started")
        while True:
            if self.stop_event.is_set():
                break
            try:
                data, addr = self.sock.recvfrom(64)
                print(f"Received data from {addr}: {data}")
                self.midi_queue.put(data)
            except Exception as e:
                pass


class MidiTransmitter(BaseTransmitter):
    def __init__(self,
                 jack_client_name: str,
                 jack_port_name: str,
                 multicast_group: str,
                 interface_ip: str,
                 multicast_ttl: int = DEFAULT_MULTICAST_TTL,
                 multicast_port: int = DEFAULT_MULTICAST_PORT,
                 buffer_size: int = None
                 ) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_ip, multicast_ttl, multicast_port, buffer_size)

        self.setup_jack()

    def setup_jack(self) -> None:
        self.client = jack.Client(self.jack_client_name)

        if not self.client:
            raise RuntimeError("Failed to create JACK client.")
        print("Client created")

        self.buffer_size = self.client.blocksize
        self.port_handle = self.client.midi_inports.register(self.jack_port_name)
        self.client.set_process_callback(self.process_callback)

    def process_callback(self, frames: int) -> None:
        for offset, data in self.port_handle.incoming_midi_events():
            print("Sending to multicast...")
            self.send_multicast(data)

class AudioReceiver(BaseReceiver):

    def __init__(self, jack_client_name: str, jack_port_name: str, multicast_group: str, interface_ip: str, multicast_ttl: int = DEFAULT_MULTICAST_TTL, multicast_port: int = DEFAULT_MULTICAST_PORT, buffer_size: int = 0) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_ip, multicast_ttl, multicast_port, buffer_size)

        self.setup_jack()
        print("Launching listener thread")
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
            audio_buffer_received = np.fromstring(audio_data, dtype=np.float32)

            # Get JACK output buffer and clear it
            output_buffer = self.output_port.get_buffer()
            output_buffer = np.zeros(self.buffer_size, dtype=np.float32)

            # Copy the received data into the buffer
            slice_length = min(len(audio_buffer_received), self.buffer_size)
            output_buffer[:slice_length] = audio_buffer_received[:slice_length]

    def listen_multicast(self) -> None:
        while True:
            if self.stop_event is not None and self.stop_event.is_set():
                print("breaking listen_multicast loop")
                break
            print("trying")
            try:
                data, addr = self.sock.recvfrom(self.buffer_size * 4) # 4 because of float32
                self.queue.put(data)
                print("queue put ok")
            except Exception as e:
                print(e)
                pass

class AudioTransmitter(BaseTransmitter):

    def __init__(self, jack_client_name: str, jack_port_name: str, multicast_group: str, interface_ip: str, multicast_ttl: int = DEFAULT_MULTICAST_TTL, multicast_port: int = DEFAULT_MULTICAST_PORT, buffer_size: int = 0) -> None:
        super().__init__(jack_client_name, jack_port_name, multicast_group, interface_ip, multicast_ttl, multicast_port, buffer_size)
        print("instantiating audio transmitter")
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


def main() -> None:
    default_client_name = "JackNetBridge"
    parser = argparse.ArgumentParser(description='Send and receive Jack audio and MIDI as multicast network streams.')
    parser.add_argument('--mode', choices=['audio_send', 'audio_recv', 'midi_send', 'midi_recv'], required=True, help='Mode of operation.')
    parser.add_argument('--jack-client', default=default_client_name, help='Name of the JACK client to register.')
    parser.add_argument('--jack-port', default=None, help='Name of the JACK port to register.')
    parser.add_argument('--multicast-group', required=True, help='Multicast group for sending/receiving data.')
    parser.add_argument('--multicast-port', type=int, default=DEFAULT_MULTICAST_PORT, help='Port number for multicast.')
    parser.add_argument('--multicast-ttl', type=int, default=DEFAULT_MULTICAST_TTL, help='Time-To-Live for multicast packets.')
    parser.add_argument('--interface-ip', required=True, help='Network interface IP address to use for multicast.')
    parser.add_argument('--buffer-size', type=int, default=DEFAULT_BUFFER_SIZE, help='Buffer size for audio data.')

    args = parser.parse_args()

    jack_client_name = args.jack_client

    if jack_client_name == default_client_name:
        if "midi" in args.mode:
            jack_client_name += "MIDI"
        elif "audio" in args.mode:
            jack_client_name += "Audio"

        if "send" in args.mode:
            jack_client_name += "Transmitter"
        elif "recv" in args.mode:
            jack_client_name += "Receiver"
        jack_client_name += f"_{args.multicast_group}:{args.multicast_port}"

    jack_port_name = args.jack_port
    if jack_port_name is None and "send" in args.mode:
        jack_port_name = "in"
    elif jack_port_name is None and "recv" in args.mode:
        jack_port_name = "out"


    # Instantiate and start the appropriate daemon based on the mode.
    if args.mode == 'midi_send':
        daemon = MidiTransmitter(
            jack_client_name,
            jack_port_name,
            args.multicast_group,
            args.interface_ip,
            args.multicast_ttl,
            args.multicast_port,
            args.buffer_size
            )
    elif args.mode == 'midi_recv':
        daemon = MidiReceiver(
            jack_client_name,
            jack_port_name,
            args.multicast_group,
            args.interface_ip,
            args.multicast_ttl,
            args.multicast_port,
            args.buffer_size
            )
    elif args.mode == 'audio_send':
        daemon = AudioTransmitter(
            jack_client_name,
            jack_port_name,
            args.multicast_group,
            args.interface_ip,
            args.multicast_ttl,
            args.multicast_port,
            args.buffer_size
            )
    elif args.mode == 'audio_recv':
        daemon = AudioReceiver(
            jack_client_name,
            jack_port_name,
            args.multicast_group,
            args.interface_ip,
            args.multicast_ttl,
            args.multicast_port,
            args.buffer_size
            )

    daemon.start()

if __name__ == "__main__":
    main()

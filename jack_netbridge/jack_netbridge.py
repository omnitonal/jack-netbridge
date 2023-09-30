import toml
import time
import threading
import argparse
import os
from .lib import MidiTransmitter, MidiReceiver, AudioTransmitter, AudioReceiver


class Manager:

    def __init__(self, config_file):
        self.config_file = config_file
        self.processes = []
        self.threads = []
        self.stop_event = threading.Event()
        self.clients = {}

    def load_config(self):
        with open(self.config_file, 'r') as f:
            raw_config = toml.load(f)

        self.clients = {}
        for client_and_port, values in raw_config.items():
            client_name, port_name = client_and_port.split(':')
            client_type = values['type']

            common_args = (
                client_name,
                port_name,
                values['multicast_group'],
                values['interface_name'],
                values['multicast_ttl'],
                values['multicast_port'],
                values.get('buffer_size', None)  # Assuming buffer_size might be optional
            )

            if client_type == 'MidiTransmitter':
                self.clients[client_and_port] = MidiTransmitter(*common_args)
            elif client_type == 'MidiReceiver':
                self.clients[client_and_port] = MidiReceiver(*common_args)
            elif client_type == 'AudioTransmitter':
                self.clients[client_and_port] = AudioTransmitter(*common_args)
            elif client_type == 'AudioReceiver':
                self.clients[client_and_port] = AudioReceiver(*common_args)
            else:
                print(f"Warning: Unknown client type '{client_type}' for {client_and_port}. Skipping...")

            self.clients[client_and_port].stop_event = self.stop_event

        return self.clients

    def start_clients(self):
        self.load_config()
        for name, client in self.clients.items():
            t = threading.Thread(target=self.worker, args=(client,))
            t.start()
            self.threads.append(t)

    def worker(self, client):
        client.start()  # Assuming each client has a 'start' method.

    def terminate_clients(self):
        self.stop_event.set()  # Signal all threads to stop
        for t in self.threads:
            t.join()  # Wait for each thread to finish

    def run(self):
        try:
            self.start_clients()
            while not self.stop_event.is_set():  # Loop until the stop_event is set
                time.sleep(1)
        except KeyboardInterrupt:
            print("Terminating clients...")
            self.terminate_clients()

def main():
    parser = argparse.ArgumentParser(description="jack_netbridge: send/receive Jack audio and MIDI as multicast streams")
    parser.add_argument('-c', '--config', type=str, default=os.path.expanduser("~/.jack_netbridge.toml"),
                        help="Path to the configuration file.")
    args = parser.parse_args()

    manager = Manager(args.config)
    manager.run()

if __name__ == "__main__":
    main()
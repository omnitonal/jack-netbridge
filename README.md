# jack_netbridge

`jack_netbridge` is a Python tool to send and receive Jack audio and MIDI as multicast network streams. This is useful for transmitting audio or MIDI over a network with minimal latency using the JACK audio system.

## Installation

```
pip install jack-netbridge
```

## Usage

```bash
usage: jack_netbridge [-h] [-c CONFIG]

jack_netbridge: send/receive Jack audio and MIDI as multicast streams

options:
  -h, --help                      Show this help message and exit.
  -c CONFIG, --config CONFIG      Path to the configuration file.
```

## Configuration file example

By default `jack_netbridge` will look for the `~/.jack_netbridge.toml` file to read configuration. Each section in the TOML file describes a client and a port with arbitrary names, separated by `:`.

Configuration example:

```
["audio_recv_L:out"]
type = "AudioReceiver"
multicast_group = "239.0.0.1"
multicast_port = 4023
multicast_ttl = 2
interface_name = "eth1"

["audio_recv_R:out"]
type = "AudioReceiver"
multicast_group = "239.0.0.1"
multicast_port = 4024
multicast_ttl = 2
interface_name = "eth1"

["midi_recv_R:in"]
type = "MidiTransmitter"
multicast_group = "239.0.0.1"
multicast_port = 4025
multicast_ttl = 2
interface_name = "eth1"

```

## Troubleshooting

* Garbled audio: make sure that both sample rate and buffer size are identical for both receiver and transmitter.

* No data sent or received: check if the current multicast group is sent / received on the right interface, e. g by checking `ip route` output.

## Contribution

We welcome contributions to improve this project. Please submit issues and pull requests on the GitHub page.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Feedback and Issues

If you encounter any issues or would like to give feedback, please open an issue on the GitHub repository.

## See also:

- [jack-netbridge: Send Your JACK Audio/MIDI as Multicast Network Streams](https://www.omnitonal.com/jack-netbridge-send-your-jack-audio-midi-as-multicast-network-streams/)
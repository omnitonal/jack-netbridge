# jack_netbridge

`jack_netbridge` is a Python tool to send and receive Jack audio and MIDI as multicast network streams. This is useful for transmitting audio or MIDI over a network with minimal latency using the JACK audio system.

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/your-username/jack_netbridge.git
   ```

2. Navigate to the cloned directory:
   ```
   cd jack_netbridge
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

```bash
usage: jack_netbridge [-h] --mode {audio_send,audio_recv,midi_send,midi_recv}
                      [--jack-client JACK_CLIENT] [--jack-port JACK_PORT]
                      --multicast-group MULTICAST_GROUP
                      [--multicast-port MULTICAST_PORT]
                      [--multicast-ttl MULTICAST_TTL] --interface-ip
                      INTERFACE_IP [--buffer-size BUFFER_SIZE]
```

### Options:

- `-h, --help`: Show the help message and exit.
- `--mode {audio_send,audio_recv,midi_send,midi_recv}`: The mode of operation.
- `--jack-client JACK_CLIENT`: Name of the JACK client to register.
- `--jack-port JACK_PORT`: Name of the JACK port to register.
- `--multicast-group MULTICAST_GROUP`: Multicast group for sending/receiving data.
- `--multicast-port MULTICAST_PORT`: Port number for multicast.
- `--multicast-ttl MULTICAST_TTL`: Time-To-Live for multicast packets.
- `--interface-ip INTERFACE_IP`: Network interface IP address to use for multicast.
- `--buffer-size BUFFER_SIZE`: Buffer size for audio data.

## Examples

To send audio:

```bash
jack_netbridge --mode audio_send --jack-client AudioSender --jack-port AudioOut --multicast-group 239.0.0.1 --interface-ip 192.168.1.10
```

To receive audio:

```bash
jack_netbridge --mode audio_recv --jack-client AudioReceiver --jack-port AudioIn --multicast-group 239.0.0.1 --interface-ip 192.168.1.11
```

## Contribution

We welcome contributions to improve this project. Please submit issues and pull requests on the GitHub page.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Feedback and Issues

If you encounter any issues or would like to give feedback, please open an issue on the GitHub repository.

## See also:

- [jack-netbridge: Send Your JACK Audio/MIDI as Multicast Network Streams](https://www.omnitonal.com/jack-netbridge-send-your-jack-audio-midi-as-multicast-network-streams/)
# LAN speed and cable diagnostics

Inspect link speed, duplex mode and error counters; run bidirectional iperf3 tests and optional cable diagnostics.

## Availability

- Category: Network and system
- Status: Available; real-system acceptance pending
- Risk: medium

## Command line

```bash
mint-toolbox --run andrew-lan-speed-test.sh --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Inspect network adapter and link

The script may install missing packages and ask for a test IP address.

Confirmation level: medium.


### Test connection to another device

Run an iperf3 server on the peer. Dependencies may need installation.

Confirmation level: medium.

- Peer IP address or hostname: text; required

### Start a speed-test server

Starts a local iperf3 listener. Close the terminal to stop it.

Confirmation level: medium.


### Test network cable

Cable diagnostics may interrupt connectivity. Do not run over SSH.

Confirmation level: high.


## Requirements and effects

Requires ethtool, iperf3 and iproute2. The script can install missing packages. Cable tests can disconnect the adapter and are refused over SSH. For throughput tests, run iperf3 -s on the peer.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.

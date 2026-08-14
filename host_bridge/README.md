# UTM Android Host Bridge

This bridge accepts one JSON object per line and injects the event into the
Android guest selected by ADB. It can consume standard input for batch use or
run as a persistent Unix socket service for host producers.

Messages may include `timestampMs`, expressed as Unix epoch milliseconds.
Timestamped events older than 30 seconds are rejected by default so delayed
sensor samples are not replayed after an ADB reconnect.

## Motion sensors

```json
{"type":"motion","accelerometer":[0,9.80665,0],"magnetometer":[0,5.9,-48.4],"gyroscope":[0,0,0]}
```

Values use Android sensor units:

- Accelerometer: m/s^2
- Magnetometer: microtesla
- Gyroscope: rad/s

The guest command is `cuttlefish_sensor_injection motion ...`. It switches the
AIDL Sensors HAL to data-injection mode for the event.

## Display rotation

```json
{"type":"rotation","degrees":90}
```

Valid values are `0`, `90`, `180`, and `270`.

## Location

```json
{"type":"location","latitude":37.3318,"longitude":-122.0312,"accuracy":3.5}
{"type":"location-reset"}
```

The bridge creates an Android GPS test provider named `gps`, enables location,
and injects latitude, longitude, and horizontal accuracy. The image declares
the GPS feature for application compatibility, but locations are unavailable
until a host producer sends an event.

The provider is a framework test provider, not a native GNSS HAL. It does not
provide satellite measurements, NMEA, carrier assistance, or hardware GNSS
attestation.

## Battery test state

```json
{"type":"battery","level":75,"status":2,"present":true,"acPowered":true,"temperature":31.2}
{"type":"battery-reset"}
```

Battery events use Android's framework test override. They improve application
testing but do not create a kernel power-supply device. Optional fields are
`present`, `acPowered`, `usbPowered`, `wirelessPowered`, and `temperature`
(degrees Celsius).

## Usage

Batch mode:

```shell
host_bridge/bridge.py --serial 127.0.0.1:5555 < events.jsonl
```

Persistent service mode:

```shell
host_bridge/bridge.py \
  --adb /path/to/platform-tools/adb \
  --serial 127.0.0.1:5555 \
  --listen /tmp/openmobile-host-bridge.sock \
  --status-file /tmp/openmobile-host-bridge-status.json
```

Send an event from any producer:

```shell
printf '{"type":"rotation","degrees":90,"timestampMs":%s}\n' \
  "$(($(date +%s) * 1000))" |
  nc -U /tmp/openmobile-host-bridge.sock
```

The service checks ADB every 10 seconds. A failed command triggers `adb
connect`, `wait-for-device`, and up to three retries. These values are
configurable with `--health-interval`, `--retries`, `--retry-delay`, and
`--command-timeout`. Send `{"type":"health"}` for an explicit guest check.

The status file is replaced atomically and reports `starting`, `ready`,
`error`, or `stopped`, together with the last event type or ADB error.

Use `--dry-run` to validate input and inspect generated ADB commands. Set
`--health-interval 0` with dry-run server mode to avoid periodic health output.

ADB must be online and authorized. On a `user` build, accept the debugging
authorization prompt in Android before starting the bridge.

## Start at login on macOS

Copy `com.openmobile.host-bridge.plist.example` to
`~/Library/LaunchAgents/com.openmobile.host-bridge.plist`, replace
`__REPOSITORY__` and `__ADB__` with absolute paths, then load it:

```shell
launchctl bootstrap gui/"$(id -u)" \
  ~/Library/LaunchAgents/com.openmobile.host-bridge.plist
```

The launch agent keeps the bridge alive. Producers can stop and reconnect
without restarting it. The socket is mode `0600`, so only the current macOS
user can inject events.

The JSON protocol is transport-independent. A future bridge can carry the same
messages over VirtIO console or VSOCK without changing event producers.

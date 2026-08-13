# UTM Android Host Bridge

This bridge accepts one JSON object per line on standard input and injects the
event into the Android guest selected by ADB.

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

## Battery test state

```json
{"type":"battery","level":75,"status":2}
{"type":"battery-reset"}
```

Battery events use Android's framework test override. They improve application
testing but do not create a kernel power-supply device or a hardware Health HAL.

## Usage

```shell
host_bridge/bridge.py --serial 127.0.0.1:5555 < events.jsonl
```

Use `--dry-run` to validate input and inspect generated ADB commands.

The JSON protocol is transport-independent. A future bridge can carry the same
messages over VirtIO console or VSOCK without changing event producers.

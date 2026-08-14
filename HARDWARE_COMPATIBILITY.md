# Hardware Compatibility

This image prioritizes broad Android application compatibility while keeping
hardware claims aligned with capabilities that can actually be supplied.

## Implemented

| Capability | Implementation | Fidelity |
|------------|----------------|----------|
| CPU and memory | Apple Silicon HVF, 4 vCPUs, 4 GiB RAM | High for generic ARM64 |
| Display | VirtIO GPU, software-compatible UTM scanout | Functional, no phone GPU identity |
| Wi-Fi APIs | VirtWifi backed by VirtIO Ethernet | Network-compatible, no 802.11 radio |
| Motion sensors | Cuttlefish Sensors HAL plus host injection | High when bridge is active |
| Location | GPS test provider plus host injection | App-level location only |
| Camera | Android external camera provider plus UVC/V4L2 | High with external UVC camera |
| Audio | Generic Android audio HAL and AC97 | Functional, not handset DSP/audio routing |
| Bluetooth | Android HCI HAL; requires a passed-through adapter | High with supported USB hardware |
| Battery state | Framework override through the host bridge | App testing only |
| Health and power | Cuttlefish Health HAL and generic Power HAL | Virtual-device semantics |
| Input | USB tablet, mouse, keyboard, and multitouch conversion | Functional |

## Device Identity

- Public product identity uses the project-owned `OpenMobile` brand while the
  internal device name remains `virtio_arm64only`.
- User builds use persistent private release keys on the build runner.
- Build username and hostname are normalized to `android` and `buildhost`.
- Extracted UTM bundles must be personalized with `tools/personalize-utm.py`
  before import so cloned instances do not share UUID and MAC addresses.
- The identity remains explicitly virtual. It does not claim to be a Pixel,
  Samsung, or other certified physical model.

## Intentionally Not Claimed

The following require physical security hardware or radio infrastructure and
cannot be faithfully emulated by a general QEMU virtual machine:

- cellular baseband, SIM/eSIM identity, IMS, emergency calling, and carrier
  provisioning;
- TrustZone, StrongBox, hardware-backed KeyMint, verified hardware attestation,
  and Play Integrity hardware verdicts;
- Widevine L1 and protected media paths;
- NFC, secure element, UWB, and handset radio calibration;
- physical vibrator, thermal zones, ambient light, proximity, and biometric
  sensors unless dedicated host hardware and matching HAL bridges are added;
- a vendor phone GPU, ISP, modem DSP, or other SoC-specific accelerator.

## Recommended Next Steps

1. Add a native VSOCK or VirtIO-serial service for sensors and location so
   injection does not depend on ADB authorization.
2. Add macOS CoreMotion and CoreLocation producers for the host bridge.
3. Pass through external UVC cameras and USB Bluetooth adapters where native
   hardware behavior matters.
4. Add dedicated virtual HALs only when a reliable host data source exists.
   Declaring unsupported hardware usually reduces compatibility by causing apps
   to select code paths that cannot complete.

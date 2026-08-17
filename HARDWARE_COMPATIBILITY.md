# Hardware Compatibility

This image prioritizes broad Android application compatibility while keeping
hardware claims aligned with capabilities that can actually be supplied.

## Implemented

| Capability | Implementation | Fidelity |
|------------|----------------|----------|
| CPU and memory | Apple Silicon HVF; 4 vCPU/4 GiB default or 8 vCPU/16 GiB compatibility profile | High for generic ARM64 |
| Display | VirtIO GPU; optional 1280 x 2856 at 495 DPI logical profile | Functional, no LTPO panel or phone GPU identity |
| Wi-Fi APIs | VirtWifi backed by VirtIO Ethernet | Network-compatible, no 802.11 radio |
| Motion sensors | Cuttlefish Sensors HAL plus host injection | High when bridge is active |
| Location | GPS test provider plus host injection | App-level location only |
| Camera | Android external camera provider plus UVC/V4L2 | High with external UVC camera |
| Audio | Generic Android audio HAL and AC97 | Functional, not handset DSP/audio routing |
| Bluetooth | Android HCI HAL; requires a passed-through adapter | High with supported USB hardware |
| Battery state | Framework override through the host bridge | App testing only |
| Health and power | Cuttlefish Health HAL and generic Power HAL | Virtual-device semantics |
| Input | USB tablet, mouse, keyboard, and multitouch conversion | Functional |

The optional `pixel-9-pro-compat` profile aligns application-visible resource
limits and display geometry without changing the OpenMobile identity. Apply it
with `tools/personalize-utm.py` before import and
`tools/apply-display-profile.sh` after Android boots.

## Device Identity

- Public product identity uses `OpenMobile One` and `OpenMobile-S1`; the
  build-only target and device-tree name remain `virtio_arm64only`.
- The UTM compatibility profile supplies `OpenMobile` / `OpenMobile-One`
  SMBIOS values so LineageOS libinit does not replace runtime product
  properties with QEMU defaults.
- The same profile assigns a device-unique SMBIOS serial (`ro.serialno`, e.g.
  `OM…`) and an `OpenMobile` bootloader version (`ro.bootloader`) so runtime
  identity no longer reports `unknown` or `0.0.0`. Re-applying with
  `--preserve-identity` keeps the existing serial and is idempotent.
- User builds use persistent private release keys on the build runner.
- Existing release keys are never regenerated to rename their certificate
  subject because doing so would break OTA and platform-signature continuity.
- Build username and hostname are normalized to `android` and `buildhost`.
- Extracted UTM bundles must be personalized with `tools/personalize-utm.py`
  before import so cloned instances do not share UUID and MAC addresses.
- The identity does not claim to be a Pixel, Samsung, or another certified
  physical model, and does not alter hardware-attestation results.

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

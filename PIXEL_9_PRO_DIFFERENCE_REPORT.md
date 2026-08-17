# Pixel 9 Pro Difference Report

This report compares the current OpenMobile ARM64 VM profile with a physical
Google Pixel 9 Pro. It is a compatibility and research baseline, not an
identity-spoofing guide.

## Scope and Confidence

Pixel hardware facts come from Google's published specifications. Google lists
the Pixel 9 Pro device codename as `caiman`. Runtime properties such as the
fingerprint, build ID, security patch level, radio firmware, and HAL versions
change with OTA releases and must be captured from the specific physical phone
being tested.

OpenMobile values come from the build patches and compatibility documentation
in this repository. Items marked "runtime capture required" cannot be proven
from source configuration alone.

## Summary

| Area | Pixel 9 Pro | OpenMobile VM | Difference |
|---|---|---|---|
| Public identity | Google Pixel 9 Pro, `caiman` | OpenMobile One, `openmobile_one` | Intentionally different |
| CPU | Google Tensor G4, 8 physical CPU cores | 8 generic ARM64 vCPUs with compatibility profile | Core count aligned; topology and CPU identity differ |
| Memory | 16 GB RAM | 16 GiB with compatibility profile | Capacity aligned; memory hardware differs |
| Display | 1280 x 2856, 495 PPI, LTPO OLED, 1-120 Hz | 1280 x 2856 at 495 DPI logical override through VirtIO GPU | Geometry aligned; panel and refresh behavior differ |
| GPU | Tensor-integrated Mali GPU | `virtio-gpu-pci`, software-compatible renderer | Different driver, extensions and performance |
| Cellular | Physical 4G/5G modem, nano-SIM and eSIM | None | Not emulated |
| Wi-Fi | Wi-Fi 7 tri-band radio | VirtWifi over virtual Ethernet | API-compatible networking, no Wi-Fi radio |
| Bluetooth | Bluetooth 5.3 dual-antenna radio | USB adapter passthrough when configured | Host hardware dependent |
| NFC / UWB | Both present | Neither present | Not emulated |
| Location | Dual-band multi-constellation GNSS | Host-injected GPS test provider | No RF measurements or GNSS chipset |
| Camera | 50 MP + 48 MP + 48 MP rear, 42 MP front | External UVC camera provider | Camera IDs, optics, metadata and ISP differ |
| Sensors | Proximity, light, accelerometer, gyro, magnetometer, barometer, temperature | Bridged motion sensors; no proximity, light, barometer or temperature | Partial |
| Battery | Physical 4700 mAh battery and charging hardware | Framework-level level, temperature, source and 4700 mAh charge-counter injection | No physical fuel gauge or charger IC |
| Security | Tensor security core, Titan M2 and Trusty TEE | Software/generic virtual security path | Hardware trust chain absent |
| DRM | Device-specific protected media path | No Widevine L1 protected path | Different security level |
| Biometrics | Fingerprint and face unlock hardware | None | Not emulated |

## Android Property Baseline

| Property family | Pixel 9 Pro expected value | OpenMobile configured value | Notes |
|---|---|---|---|
| `ro.product.*.brand` | `google` | `OpenMobile` | Stable product identity |
| `ro.product.*.manufacturer` | `Google` | `OpenMobile` | Stable product identity |
| `ro.product.*.model` | `Pixel 9 Pro` | `OpenMobile One` in the build, `OpenMobile-One` at runtime | SMBIOS-safe OpenMobile identity |
| `ro.product.*.device` | `caiman` | `openmobile_one` | Pixel codename is documented by Google |
| `ro.product.*.name` | Build-variant dependent, normally based on `caiman` | `openmobile_one` | Capture the physical phone |
| `ro.*.build.fingerprint` | Google-signed, OTA-version dependent | OpenMobile private release build | Never compare against a hard-coded old Pixel fingerprint |
| `ro.build.version.release` | OTA-version dependent | Android 16 / LineageOS 23.2 build | Capture both devices on the test date |
| `ro.build.version.security_patch` | OTA-version dependent | LineageOS source state | Capture both devices |
| `ro.soc.manufacturer` | Google | OpenMobile | Runtime value should be confirmed |
| `ro.soc.model` | Tensor G4 family value | `OpenMobile-S1` | Property text does not establish hardware equivalence |
| `ro.hardware*` | Pixel platform-specific values | VirtIO/QEMU platform-specific values | Low-level values must remain truthful |
| `ro.boot.*` | Pixel bootloader and verified-boot state | `OpenMobile-1.0` bootloader and unique serial via SMBIOS; verified-boot state stays truthful (`orange`) | Boot chain and attestation are not spoofed |

## Implemented Compatibility Improvements

The optional `pixel-9-pro-compat` profile now provides:

- 8 virtual CPUs and 16 GiB guest memory in the UTM configuration;
- stable UTM display sizing while the profile is active;
- a 1280 x 2856 Android logical display at 495 DPI;
- a reversible display override through `tools/apply-display-profile.sh`;
- a device-unique SMBIOS serial (`ro.serialno`) and an `OpenMobile` bootloader
  version (`ro.bootloader`), replacing the `unknown` / `0.0.0` defaults; and
- a `capacityMah` battery event field that maps 4700 mAh and the current level
  to Android's charge-counter test value.

Apply the resource profile before importing the VM:

```shell
tools/personalize-utm.py LineageOS_on_arm64.utm \
  --hardware-profile pixel-9-pro-compat
```

Apply the display profile after boot:

```shell
tools/apply-display-profile.sh \
  --serial 127.0.0.1:5555 pixel-9-pro-compat
```

Inject the Pixel 9 Pro battery-capacity baseline:

```json
{"type":"battery","level":80,"status":2,"present":true,"capacityMah":4700}
```

## Feature and HAL Differences

### Present or approximately testable

- ARM64 application ABI.
- Touchscreen and multitouch application APIs.
- Accelerometer, gyroscope and magnetometer behavior when host injection is
  active.
- App-level location behavior when host location injection is active.
- External camera workflows through a passed-through UVC camera.
- Bluetooth APIs when a compatible USB Bluetooth adapter is passed through.
- Battery percentage, temperature and charging-state application flows through
  framework injection.

### Fundamentally different

- Tensor G4 CPU/GPU/NPU behavior and performance counters.
- Pixel camera HAL, sensor calibration, ISP pipeline and proprietary camera
  features.
- Cellular telephony, modem firmware, carrier provisioning, SIM/eSIM and IMS.
- Wi-Fi scan/ranging/radio characteristics, Wi-Fi 7 and antenna behavior.
- NFC secure element and UWB ranging.
- Titan M2, Trusty, hardware-backed KeyMint, StrongBox and attestation.
- Widevine L1 and protected display/media paths.
- Physical biometrics, proximity, ambient light, barometer, temperature and
  thermal zones.

## Runtime Capture Procedure

Collect both devices with the same platform-tools version:

```shell
tools/collect-android-profile.sh --serial PIXEL_SERIAL pixel9pro-profile
tools/collect-android-profile.sh --serial 127.0.0.1:5555 openmobile-profile
```

Compare the normalized text artifacts:

```shell
diff -ru pixel9pro-profile openmobile-profile
```

The collection intentionally excludes user accounts, app data, serial numbers,
MAC addresses, IMEI, MEID and other per-device identifiers.

## Interpretation Rules

1. Treat different build fingerprints as expected; they identify independently
   signed software releases.
2. Do not infer hardware equivalence from editable `ro.product.*` strings.
3. Prefer PackageManager features, HAL declarations and `dumpsys` output over
   marketing names.
4. Treat attestation and DRM results as security-bound observations that cannot
   be reproduced by changing properties.
5. Record the test date and both OTA build IDs because Pixel runtime values
   change over time.

## Sources

- Google Pixel 9 Pro technical specifications:
  https://store.google.com/gb/product/pixel_9_pro_specs?hl=en-GB
- Google Pixel OTA images and device codename (`caiman`):
  https://developers.google.com/android/ota#caiman
- OpenMobile implementation baseline:
  `HARDWARE_COMPATIBILITY.md`
- OpenMobile product property configuration:
  `patches/0007-virtio-arm64-consistent-product-identity.patch`

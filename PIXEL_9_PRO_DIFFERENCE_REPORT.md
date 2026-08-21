# Pixel 9 Pro Difference Report

This report compares the ARM64 VM profile with a physical Google Pixel 9 Pro.
The VM is now configured to present a Pixel 9 Pro (`caiman`) software identity
across build, SMBIOS and runtime layers for local research. This aligns
reported strings only; it does not create the Pixel hardware trust chain
(verified boot, key attestation, StrongBox, Widevine L1), which a QEMU VM
cannot supply.

## Scope and Confidence

Pixel hardware facts come from Google's published specifications. Google lists
the Pixel 9 Pro device codename as `caiman`. Runtime properties such as the
fingerprint, build ID, security patch level, radio firmware, and HAL versions
change with OTA releases and must be captured from the specific physical phone
being tested.

The VM values come from the build patches, the SMBIOS profile in
`tools/personalize-utm.py`, and the runtime resetprop module in
`magisk/pixel-9-pro-identity/`. Items marked "runtime capture required" cannot
be proven from source configuration alone.

## Summary

| Area | Pixel 9 Pro | Configured VM identity | Difference |
|---|---|---|---|
| Public identity | Google Pixel 9 Pro, `caiman` | Google Pixel 9 Pro, `caiman` (build + SMBIOS + resetprop) | String identity aligned; hardware trust chain absent |
| CPU | Google Tensor G4, 8 physical CPU cores | 8 generic ARM64 vCPUs with compatibility profile | Core count aligned; topology and CPU identity differ |
| Memory | 16 GB RAM | Up to 16 GiB, auto-capped to a safe share of host RAM | Capacity aspirational; capped so the guest never starves the macOS host |
| Display | 1280 x 2856, 495 PPI, LTPO OLED, 1-120 Hz | 1280 x 2856 at 495 DPI logical override through VirtIO GPU | Geometry aligned; panel and refresh behavior differ |
| GPU | Tensor-integrated Mali-G715 | `virtio-gpu-pci`; Mesa llvmpipe/lavapipe reports `ARM` / `Mali-G715` | Public name aligned; driver, extensions and performance differ |
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

| Property family | Pixel 9 Pro expected value | Configured VM value | Notes |
|---|---|---|---|
| `ro.product.*.brand` | `google` | `google` | Build override + resetprop |
| `ro.product.*.manufacturer` | `Google` | `Google` | Build override + resetprop |
| `ro.product.*.model` | `Pixel 9 Pro` | `Pixel 9 Pro` | build.prop + resetprop; SMBIOS carries space-free `caiman` |
| `ro.product.*.device` | `caiman` | `caiman` | `DeviceProduct/DeviceName` override + resetprop |
| `ro.product.*.name` | Build-variant dependent, normally based on `caiman` | `caiman` | Confirm against the physical phone |
| `ro.*.build.fingerprint` | Google-signed, OTA-version dependent | `google/caiman/caiman:16/BP4A.260205.001/13561507:user/release-keys` | Signed with private release keys, not Google keys; update to the current OTA when captured |
| `ro.build.version.release` | OTA-version dependent | `16` | Capture both devices on the test date |
| `ro.build.version.security_patch` | OTA-version dependent | `2026-02-05` via resetprop | Keep in sync with the mirrored OTA |
| `ro.soc.manufacturer` | Google | `Google` | Build override + resetprop |
| `ro.soc.model` | `zumapro` (Tensor G4 platform) | `zumapro` (build.prop + resetprop) | Property text does not establish hardware equivalence |
| `ro.hardware*` | Pixel platform-specific values | `caiman` reported via resetprop; HAL resolution stays on the real VirtIO/QEMU platform | String aligned; kernel cmdline unchanged to avoid HAL bootloop |
| `ro.boot.*` | Pixel bootloader and verified-boot state | `ripcurrentpro-*` bootloader and unique serial via SMBIOS; `verifiedbootstate` string set to `green` by resetprop while the real AVB state stays `orange` | Boot chain and attestation are not spoofed |

## Implemented Compatibility Improvements

The optional `pixel-9-pro-compat` profile now provides:

- 8 virtual CPUs and up to 16 GiB guest memory, auto-capped to a safe share of
  host RAM so the macOS host keeps headroom;
- stable UTM display sizing while the profile is active;
- a 1280 x 2856 Android logical display at 495 DPI;
- a reversible display override through `tools/apply-display-profile.sh`;
- a device-unique SMBIOS serial (`ro.serialno`) and a `ripcurrentpro-*`
  bootloader version (`ro.bootloader`), replacing the `unknown` / `0.0.0`
  defaults; and
- a `capacityMah` battery event field that maps 4700 mAh and the current level
  to Android's charge-counter test value.

The Pixel 9 Pro (`caiman`) software identity is applied in three layers:

- **Build**: `patches/0007-virtio-arm64-consistent-product-identity.patch` sets
  `PRODUCT_BRAND/MANUFACTURER/MODEL`, the `BuildFingerprint`, and
  `DeviceName/DeviceProduct=caiman`.
- **SMBIOS**: `tools/personalize-utm.py` supplies space-free
  `Google` / `caiman` DMI values plus the unique serial.
- **Runtime**: the `magisk/pixel-9-pro-identity/` module rewrites the read-only
  `ro.boot.*`, `ro.hardware`, per-partition fingerprints and
  `ro.build.version.security_patch` that build.prop cannot cover, and ships a
  `pif.json` for PlayIntegrityFix (basic-integrity only).

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

## Emulator-Detection Vector Matrix

This matrix summarizes the emulator/VM-detection signals collected from public
research (e.g. `strazzere/anti-emulator`, `samohyes/Anti-vm-in-android`, common
`Build`/`getprop` checks, and OpenGL/sensor/telephony probes) and states how
each is handled here. Note this VM is a QEMU `virt` (VirtIO) machine, not the
goldfish/ranchu Android emulator, so several classic markers do not exist to
begin with. Runtime state is verifiable with `tools/audit-fingerprint.sh`.

| Vector | Real device | This VM | Status |
|---|---|---|---|
| `Build` brand/manufacturer/model/device/product | Pixel 9 Pro / caiman | Set at build + resetprop | Fixed |
| `ro.build.fingerprint` | Google-signed | `google/caiman/...:user/release-keys` | Fixed (string); signature mismatch remains |
| `ro.board.platform` / `ro.product.board` | `zumapro` / `caiman` | `zumapro`/`caiman` baked in via libinit_virt vendor_init override | Fixed at build time (no Magisk) |
| `ro.hardware` / `ro.boot.hardware` | `zumapro`/device value | Kept truthful (`virtio`) at build time; `caiman` disguise deferred to a post-boot resetprop step. Overriding it in vendor_init caused a HAL bootloop and was removed | String disguise runtime-only |
| `ro.serialno` / `ro.bootloader` | device values | Unique SMBIOS serial + `ripcurrentpro-*` | Fixed |
| `ro.kernel.qemu`, `qemu.*`, `init.svc.qemud` | absent | Not present on the `virt` board | Not present |
| `/dev/qemu_pipe`, `/dev/socket/qemud`, `libc_malloc_debug_qemu.so`, `/sys/qemu_trace`, `qemu-props` | absent | Not created by the `virt` board (goldfish/ranchu-only) | Not present |
| `/proc/tty/drivers` goldfish, `/proc/cpuinfo` x86 | absent | ARM64 `virt`, no goldfish | Not present |
| MAC `02:00:00:00:00:00` | vendor MAC | Random locally-administered MAC per instance | Fixed |
| Sensors (accel/gyro/compass) | present | Declared via patch 0008 + host bridge | Fixed |
| GL/Vulkan renderer | `ARM` / `Mali-G715` | Public GL vendor/renderer and Vulkan device name report `ARM` / `Mali-G715`; internal Mesa vendor/driver IDs remain truthful | Public strings aligned; Mesa vendor/driver IDs, Vulkan device type, feature limits and performance remain residual tells |
| Telephony IMEI/IMSI/operator "Android"/`1555521xxxx` | carrier values | No modem emulated; no default emulator numbers either | Not emulated |
| `ro.boot.verifiedbootstate` | `green` (Google-signed) | `green` string via resetprop; real AVB stays `orange` | Cosmetic only |
| Play Integrity / key attestation / Widevine L1 | hardware-backed | Not achievable in a VM | Hard limit |

Patch `0011` aligns the public GL/Vulkan vendor and renderer strings at API
return boundaries, including the lavapipe and Venus paths. It deliberately
keeps Gallium screen identity, Vulkan vendor/driver IDs, UUIDs and pipeline
cache headers truthful so the override cannot alter driver selection or cache
semantics. The underlying Mesa software renderer, Vulkan `deviceType`, exposed
feature limits, shader behavior and performance remain distinguishable.

Patch `0012` keeps UTM's non-3D `virtio-gpu-pci` device on the Mesa software
path (`mesa_swrast`) instead of auto-switching to ANGLE/SwiftShader. The
SwiftShader advanced boot option remains available for recovery or comparison.

Other residual tells that source/property changes cannot remove are
`/proc/cpuinfo` CPU implementer, the
real `orange` verified-boot/attestation state, and the `release-keys` fingerprint
versus the private signing key. Eliminating those differences requires GPU
passthrough or physical security hardware and remains out of scope.

## Platform identity override (vendor_init)

`ro.board.platform`, `ro.product.board` and the SoC strings are read-only and
cannot be set from build.prop, but they can be overridden safely in
`vendor_init`:

- `patches/0009` adds `set_pixel_platform_identity()` to
  `device/virt/virt-common/libraries/libinit/libinit_virt.cpp`, called from
  `vendor_load_properties_virt()`. It uses `property_override()` to set
  `ro.board.platform`/`ro.product.board`=`zumapro`, `ro.product.vendor.board`,
  `ro.hardware.chipname` and `ro.soc.*`. These are consumed only as identity
  strings, never to resolve a HAL rc import path, so overriding them here is
  safe.
- **`ro.hardware`/`ro.boot.hardware` are deliberately NOT overridden here.**
  `vendor_load_properties()` runs from `PropertyInit()` ->
  `PropertyLoadBootDefaults()`, which `SecondStageMain` calls BEFORE
  `LoadBootScripts()`. `LoadBootScripts()` then expands
  `import /vendor/etc/init/hw/init.${ro.hardware}.rc`. Rewriting `ro.hardware`
  to `caiman` in vendor_init changed the early hardware service selector and
  the device bootlooped. Installing a byte-identical `init.caiman.rc` alias was
  tested and did not make the override safe, so the alias and override were
  removed together.
  (Verified against LineageOS `lineage-23.2` `system/core/init/init.cpp`
  `SecondStageMain` and `property_service.cpp`
  `PropertyLoadBootDefaults`.) `ro.hardware` therefore keeps its truthful
  `virtio` value at build time; the `caiman` string disguise, if needed, must
  be applied at runtime after boot via resetprop, which runs long after
  `LoadBootScripts()` and cannot affect HAL loading.

## Runtime Capture Procedure

Audit the running VM against the detection matrix at any time:

```shell
ADB=/opt/homebrew/bin/adb tools/audit-fingerprint.sh --serial 127.0.0.1:5555
```

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

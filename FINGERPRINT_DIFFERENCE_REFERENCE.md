# Fingerprint Difference Reference — VM vs. Physical Pixel 9 Pro

This document catalogs, per fingerprint family, how the LineageOS/QEMU
`virtio_arm64only` VM differs from a physical Google Pixel 9 Pro (`caiman`).
It is a **descriptive test-and-analysis reference**, not an anti-detection
guide: each row states the real-device value, the VM's observed value, and
whether the difference is aligned, cosmetic, or a residual virtualization tell.

The goal is honest traceability for compatibility testing and research — so a
tester can tell an *expected* VM/software difference apart from a genuine bug,
and can reason about which signals are load-bearing for app behavior.

## How to read this

- **Layer** — where the value originates: `build.prop` (static), `vendor_init`
  (early boot), `resetprop` (post-boot Magisk module), `kernel/cmdline`,
  `SMBIOS/DMI`, `PCI`, `HAL`, or `GPU driver`.
- **Status**
  - `Aligned` — VM string matches the Pixel value and the underlying behavior is
    reasonably equivalent for app-level purposes.
  - `String-aligned` — the reported string matches, but the underlying hardware
    or trust property does not; a capability probe still distinguishes them.
  - `Residual tell` — the VM exposes a value that differs from a real Pixel and
    cannot be reconciled without real hardware / passthrough.
  - `Not present` — a classic emulator marker that simply does not exist on this
    QEMU `virt` board (so there is nothing to hide).
- **Evidence** — where the observed VM value in this doc was captured from.

All VM values below were captured from the release `v2026.08.24` image
(commit `dbf999b`) via `adb shell getprop`, `/proc`, `dumpsys SurfaceFlinger`
and `cmd gpu vkjson`. Pixel values come from Google's published specs and OTA
metadata; runtime Pixel values (fingerprint, patch level) drift with each OTA
and must be re-captured from the specific phone under test.

---

## 1. Product identity (`ro.product.*`)

| Property | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| `ro.product.*.brand` | `google` | `google` | build + resetprop | Aligned |
| `ro.product.*.manufacturer` | `Google` | `Google` | build + resetprop | Aligned |
| `ro.product.*.model` | `Pixel 9 Pro` | `Pixel 9 Pro` | build + resetprop | String-aligned |
| `ro.product.*.device` | `caiman` | `caiman` | build + resetprop | String-aligned |
| `ro.product.*.name` | `caiman`-derived | `caiman` | build + resetprop | String-aligned |
| `ro.product.system.device` | `caiman` | `virtio_arm64only` | build.prop | **Residual tell** |
| `ro.product.system.name` | `caiman`-derived | `lineage_virtio_arm64only` | build.prop | **Residual tell** |

**Note.** The public per-partition identity is aligned to `caiman`, but the
LineageOS device-tree name (`virtio_arm64only`) still surfaces in
`ro.product.system.device/name` and `ro.build.flavor`. These are the build
target, not a marketing name, and were deliberately left truthful.

---

## 2. Build identity & fingerprint (`ro.build.*`, `ro.*.build.*`)

| Property | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| `ro.build.fingerprint` | Google-signed, OTA-versioned | `google/caiman/caiman:16/BP4A.260205.001/13561507:user/release-keys` | build (0007) | String-aligned |
| `ro.build.id` | OTA-versioned (e.g. `BP4A.*`) | `BP4A.251205.006` | LineageOS-derived | **Internally inconsistent** |
| `ro.build.version.incremental` | numeric OTA build | `20260824` | build | **Internally inconsistent** |
| `ro.build.version.release` | `16` | `16` | build | Aligned |
| `ro.build.version.security_patch` | OTA-versioned | `2026-02-05` (resetprop) | resetprop | String-aligned |
| `ro.build.tags` | `release-keys` | `release-keys` | build | String-aligned |
| `ro.build.type` | `user` | `user` | build | Aligned |
| `ro.build.flavor` | `caiman-user` | `lineage_virtio_arm64only-user` | build.prop | **Residual tell** |
| `ro.build.host` | Google buildhost | `buildhost` | build (`BUILD_HOSTNAME`) | Neutralized |
| `ro.build.user` | Google build acct | `android` | build (`BUILD_USERNAME`) | Neutralized |
| `ro.*.build.date` | Google build time | `Mon Aug 24 08:46:14 UTC 2026` | build (0014/0015) | Neutralized (UTC) |
| signing key | Google private keys | project private release keys | `ensure-release-keys.sh` | **Residual tell** |

**Internal inconsistency (bug-class, honestly logged).** The hardcoded
fingerprint carries build-id token `BP4A.260205.001` and incremental
`13561507`, but the image's actual `ro.build.id` is `BP4A.251205.006` and
`ro.build.version.incremental` is `20260824`. A consistency check that parses
the fingerprint (`.../<ID>/<incremental>:...`) and compares it to
`ro.build.id` / `ro.build.version.incremental` will see a mismatch. This is a
real internal inconsistency in the identity strings; it is documented here
rather than "fixed", because tightening it only serves detection-evasion.

**PII hygiene (fixed).** `ro.build.host`, `ro.build.user` and every
`ro.*.build.date` were scrubbed of build-host identity: neutral `buildhost` /
`android`, and all dates stamped in UTC (previously leaked `CST`). Verified at
runtime — see `runtime-getprop-utc-pii.txt`.

---

## 3. SoC / platform (`ro.soc.*`, `ro.board.*`, `ro.hardware.*`)

| Property | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| `ro.soc.manufacturer` | `Google` | `Google` | vendor_init (0009) | String-aligned |
| `ro.soc.model` | `zumapro` | `zumapro` | vendor_init (0009) | String-aligned |
| `ro.board.platform` | `zumapro` | `zumapro` | vendor_init (0009) | String-aligned |
| `ro.product.board` | `zumapro` | `zumapro` | vendor_init (0009) | String-aligned |
| `ro.hardware` | device value | `caiman` | bootconfig (0016) | String-aligned |
| `ro.boot.hardware` | device value | `caiman` | bootconfig (0016) | String-aligned |

**How `ro.hardware` became `caiman` (patch 0016).** `init` derives `ro.hardware`
from `androidboot.hardware` in `ExportKernelBootProps()`, which runs *before*
`LoadBootScripts()` expands `import /vendor/etc/init/hw/init.${ro.hardware}.rc`.
Patch 0016 changes the **bootconfig** value `androidboot.hardware` from `virtio`
to `caiman`, so `ro.hardware` is `caiman` from the first instant of second-stage
init — no re-set of a read-only property, no `/dev/__properties__` write (which
`system/sepolicy` `neverallow`s for every domain but `init`), no resetprop.

The earlier note that "a byte-identical `init.caiman.rc` alias did not resolve
it" applied to overriding `ro.hardware` **in `vendor_init` at runtime**, where
the `.rc` import had already been decided from the old value. 0016 avoids that
ordering trap entirely by fixing the value at its boot-config source, and
installs `init.caiman.rc`, `init.recovery.caiman.rc` and `fstab.caiman` (all
byte-identical to their `virtio` originals, which are retained) so every
`${ro.hardware}` selector still resolves. The GSI boot path is unaffected: it
selects its fstab via `androidboot.fstab_suffix=virtio.gsi.*`, a different key
that `fs_mgr` checks before `hardware`. The SoC/board strings above remain
vendor_init overrides because they are consumed only as identity, never to
resolve an rc import path.

---

## 4. Boot / verified-boot (`ro.boot.*`, `ro.bootloader`, `ro.serialno`)

| Property | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| `ro.serialno` | device serial | `55DC7A5E2B4C91` (unique per instance) | SMBIOS | String-aligned |
| `ro.bootloader` | Pixel bootloader ver | `ripcurrentpro-1.5-13561507` | SMBIOS | String-aligned |
| `ro.boot.verifiedbootstate` (kernel) | `green` (locked, Google-signed) | `orange` (real AVB state) | kernel/cmdline | **Residual tell** |
| `ro.boot.verifiedbootstate` (reported) | `green` | `green` (resetprop cosmetic) | resetprop | String-aligned only |
| `ro.boot.flash.locked` | `1` | `1` (resetprop) | resetprop | String-aligned only |
| `ro.boot.wifi_impl` | (absent) | `virt_wifi` | kernel/cmdline | **Residual tell** |
| kernel cmdline | Pixel bootchain | `androidboot.verifiedbootstate=orange`, `androidboot.wifi_impl=virt_wifi`, `androidboot.console=hvc0`, `console=ttyAMA0`, `kvm-arm.mode=protected` | kernel/cmdline | **Residual tell** |

**Trust chain is not spoofed.** The real Android Verified Boot state is
`orange` (unlocked, non-Google key). The resetprop module rewrites the reported
string to `green`, but this is cosmetic: hardware key attestation, StrongBox and
Play Integrity `DEVICE`/`STRONG` verdicts read the real AVB state and the real
(non-Google) signing key, and cannot be satisfied by a VM. `virt_wifi`,
`hvc0/ttyAMA0` console and `kvm-arm.mode=protected` on the kernel cmdline remain
VM-identifying and are not editable without breaking boot.

---

## 5. Graphics stack (SurfaceFlinger GLES, Vulkan)

| Signal | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| Vulkan `deviceName` | `Mali-G715` | `Mali-G715` | patch 0011/0013 | String-aligned |
| Vulkan `vendorID` | ARM (`0x13B5`) | `6880` = `0x1AE0` (Google/SwiftShader) | GPU driver | **Residual tell** |
| Vulkan `deviceID` | Mali device id | `49374` = `0xC0DE` (placeholder) | GPU driver | **Residual tell** |
| Vulkan `driverName` | ARM Mali driver | `SwiftShader driver` | GPU driver | **Residual tell** |
| Vulkan `deviceType` | integrated GPU | CPU (software) | GPU driver | **Residual tell** |
| GLES vendor/renderer | `ARM` / `Mali-G715` | `Google Inc. (Google), ANGLE (Google, Vulkan 1.3.0 (Mali-G715 (0x0000C0DE)), SwiftShader driver-5.0.0), OpenGL ES 3.1.0` | GPU driver | Partially aligned |
| `ro.hardware.egl` | Mali EGL | `angle` | build.prop | **Residual tell** |
| `ro.hardware.vulkan` | Mali ICD | `pastel` | build.prop | **Residual tell** |

**Why GL vendor is not forced to bare `ARM`.** SurfaceFlinger and Skia consume
`GL_VENDOR`/`GL_RENDERER` for backend and capability detection. Globally
forcing `debug.angle.gl_vendor=ARM` made Skia treat the SwiftShader/ANGLE
software backend as native Mali and produced **corrupted composition**
(that override was removed in commit `7764442`). The Vulkan `deviceName` is
aligned to `Mali-G715`, but vendor/device IDs, `driverName`, `deviceType=CPU`,
extension set, limits and performance all remain software-renderer tells. The
`Mali-G715 (0x0000C0DE)` string in the GLES line literally embeds the
placeholder device id — a direct fingerprint of the software path.

---

## 6. Display panel (`dumpsys SurfaceFlinger`, EDID)

| Signal | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| Panel | LTPO OLED, 1-120 Hz | virtual, fixed | VirtIO GPU | **Residual tell** |
| Resolution | 1280 x 2856, 495 PPI | 1280 x 2856 @ 495 DPI (logical override) | display profile | Geometry aligned |
| Display name | Pixel internal panel | `QEMU Monitor` | VirtIO GPU/EDID | **Residual tell** |
| EDID PnP id | Pixel/Samsung panel | `RHT` (Red Hat), productId `4660`, year `2014` | EDID | **Residual tell** |
| HDR / refresh | LTPO, HDR | none / fixed | VirtIO GPU | **Residual tell** |

The logical resolution/DPI are aligned so app layout matches a Pixel, but the
EDID reports a Red Hat / QEMU virtual monitor and there is no LTPO/HDR/variable
refresh behavior.

---

## 7. CPU topology (`/proc/cpuinfo`)

| Signal | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| Core count | 8 cores (1+3+4 Tensor G4) | 8 vCPUs (compat profile) | QEMU `-smp` | Count aligned |
| CPU implementer | ARM/vendor mix (big.LITTLE) | all `0x61` (Apple, via HVF) | host CPU | **Residual tell** |
| CPU part | Cortex-X/A7xx mix | all `0x000` | host CPU | **Residual tell** |
| Topology | heterogeneous 3-cluster | homogeneous, identical cores | QEMU | **Residual tell** |
| Performance counters | Tensor G4 characteristics | Apple-Silicon-under-HVF | host CPU | **Residual tell** |

A real Pixel exposes a heterogeneous big.LITTLE topology with ARM implementer
IDs and distinct part numbers per cluster. The VM exposes 8 identical cores with
implementer `0x61` (Apple) and part `0x000` — a strong, unmaskable tell that the
guest runs under Apple Silicon HVF, not Tensor.

---

## 8. Bus / device topology (PCI, block, console)

| Signal | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| PCI vendor id | Pixel SoC buses | `1AF4` (Red Hat / VirtIO) devices | PCI | **Residual tell** |
| Network | Pixel Wi-Fi/modem | `virtio_net` + `virt_wifi` | HAL/kernel | **Residual tell** |
| GPU device | Mali (SoC-integrated) | `virtio-gpu-pci` | PCI | **Residual tell** |
| Block devices | UFS `sd*`/`dm-*` | `vda`, `vdb` (virtio-blk) + `dm-*` | kernel | **Residual tell** |
| Boot firmware | Pixel bootloader | EDK2 EFI (`/mnt/vendor/EFI` on `vda1`) | firmware | **Residual tell** |
| Console | (none exposed) | `hvc0`, `hvc1`, `ttyAMA0` | kernel/cmdline | **Residual tell** |
| Kernel | Pixel Tensor kernel | `6.12` generic ARM64 `virt` | kernel | **Residual tell** |

`/sys/bus/virtio`, PCI `1AF4:*` device IDs, virtio block/net/gpu drivers, the
EDK2/EFI partition layout and hypervisor console ports are the actual virtual
hardware interfaces. They are not string properties and cannot be renamed
without replacing the emulated devices; they are the most robust VM evidence
available to a privileged/root probe.

---

## 9. LineageOS / ROM provenance

| Signal | Pixel 9 Pro | VM (observed) | Layer | Status |
|---|---|---|---|---|
| `ro.lineage.*` | (absent on stock) | `23.2-...-virtio_arm64only`, `UNOFFICIAL` | build.prop | **Residual tell** |
| `ro.lineage.releasetype` | (absent) | `UNOFFICIAL` | build.prop | **Residual tell** |
| Cuttlefish HAL overlay | (absent) | sensors/health HALs from Cuttlefish | vendor | **Residual tell** |
| `ro.build.description` | Google desc | `lineage_virtio_arm64only-user ...` | build.prop | **Residual tell** |

The presence of any `ro.lineage.*` property, `UNOFFICIAL` release type, and
Cuttlefish-derived HALs identify this as a LineageOS research build rather than
stock Pixel firmware. These are truthful provenance markers.

---

## 10. HAL / radio capability

| Capability | Pixel 9 Pro | VM | Status |
|---|---|---|---|
| Cellular / modem / SIM / IMS | present | none emulated | **Residual tell** |
| Wi-Fi radio (802.11, ranging) | Wi-Fi 7 | `virt_wifi` over virtual Ethernet | **Residual tell** |
| NFC / secure element / UWB | present | absent | **Residual tell** |
| Bluetooth radio | BT 5.3 | USB passthrough only | Host-dependent |
| Biometrics (fingerprint/face) | present | absent | **Residual tell** |
| Sensors: proximity/light/baro/temp | present | absent (only accel/gyro/compass bridged) | **Residual tell** |
| GNSS chipset | multi-constellation | GPS test provider only | **Residual tell** |
| KeyMint / StrongBox / Titan M2 | hardware-backed | software / absent | **Residual tell** |
| Widevine L1 | present | L3 / none | **Residual tell** |
| Camera ISP / Pixel camera HAL | present | external UVC provider | **Residual tell** |

These are capability-level differences: `PackageManager.hasSystemFeature()`,
HAL declarations and `dumpsys` output reveal them regardless of property
strings, which is exactly why the Interpretation Rules below prefer capability
probes over marketing names.

---

## Summary by observability layer

| Layer visible to… | Aligned / neutralized | Residual tells |
|---|---|---|
| Ordinary app (properties, PackageManager, GL/Vulkan name) | product identity, build strings (mostly), Vulkan device name, display geometry, PII/UTC, `ro.hardware=caiman` (0016) | fingerprint↔build.id inconsistency, Vulkan IDs/driver/type, missing HAL features |
| Shell / privileged app | + resetprop-adjusted boot strings | `ro.lineage.*`, `virt_wifi`, `hvc*`, `vda/vdb`, Cuttlefish HALs |
| Root / kernel | — | `/sys/bus/virtio`, PCI `1AF4:*`, EDK2/EFI, CPU implementer `0x61`, `orange` AVB |

## Interpretation rules

1. Different build fingerprints are expected; they identify independently
   signed software releases, not hardware.
2. Do not infer hardware equivalence from editable `ro.product.*` strings.
3. Prefer `PackageManager` features, HAL declarations and `dumpsys` output over
   marketing names.
4. Attestation, StrongBox and Widevine L1 results are security-bound and cannot
   be reproduced by editing properties; treat `orange` AVB and the non-Google
   signing key as ground truth.
5. Record the test date and both OTA build IDs, since Pixel runtime values drift
   with every OTA.

## Evidence sources

- Runtime `getprop`, `/proc/cpuinfo`, `/proc/mounts`, `/proc/cmdline`:
  `/tmp/final-getprop.txt`, `/tmp/final-lowlevel.txt` (captured from the image
  family), and `artifacts/android/pii-utc-32707426468/runtime-evidence/`.
- Graphics: `dumpsys SurfaceFlinger` GLES line and `cmd gpu vkjson`
  (`/tmp/final-graphics-kernel.txt`).
- Build-product PII/UTC evidence: `runtime-getprop-utc-pii.txt`,
  `buildprop-utc-pii-evidence.txt`.
- Configuration sources: `patches/0007`, `0009`, `0011`, `0013`,
  `tools/personalize-utm.py`, `magisk/pixel-9-pro-identity/`.
- Companion documents: `PIXEL_9_PRO_DIFFERENCE_REPORT.md` (feature/HAL summary),
  `HARDWARE_COMPATIBILITY.md` (capability fidelity).
- Pixel 9 Pro specs and codename (`caiman`): Google published specifications and
  OTA metadata.

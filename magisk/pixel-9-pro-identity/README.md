# Pixel 9 Pro Runtime Identity (Magisk module)

This module aligns **runtime read-only properties** of the LineageOS/QEMU VM
with a Google Pixel 9 Pro (`caiman`), for local research on this virtual device.
It complements the build-time identity set by
`patches/0007-virtio-arm64-consistent-product-identity.patch` and the SMBIOS
identity set by `tools/personalize-utm.py`.

## What it changes

`post-fs-data.sh` runs before the framework starts and uses `resetprop` to set:

- per-partition `ro.product.*` brand / manufacturer / model / device / name;
- per-partition `ro.*.build.fingerprint` plus `ro.build.id`,
  `display.id`, `description`, `flavor`, `version.incremental`,
  `version.release`, `version.security_patch`, `tags`, `type`;
- `ro.hardware`, `ro.boot.hardware*`, `ro.soc.*`, and the SoC platform/board
  (`ro.board.platform=zumapro`, `ro.product.board=caiman`);
- cosmetic `ro.boot.verifiedbootstate` / `flash.locked` string fields;
- deletion of any leaked QEMU marker properties (`ro.kernel.qemu`, `qemu.*`,
  `init.svc.qemud`, `init.svc.qemu-props`) and a device-style `net.hostname`.

`ro.boot.*` and `ro.hardware` originate from the kernel cmdline / DMI, not
`build.prop`, so `resetprop` in `post-fs-data` is the only reliable place to
correct them. The kernel cmdline is intentionally **not** changed: `init`
resolves HAL module paths from `ro.hardware` during early boot, and pointing it
at a non-existent `caiman` HAL set would bootloop the VM.

## Install

1. Root the VM's `boot.img` with Magisk (see the repository `README.md`).
2. Copy this directory into `/data/adb/modules/pixel_9_pro_identity` (or zip it
   and flash through the Magisk app).
3. For Play Integrity basic verdict, also install **PlayIntegrityFix** and copy
   `pif.json` from this directory to its config location
   (`/data/adb/modules/playintegrityfix/pif.json` or
   `/data/adb/pif.json`, depending on the fork).
4. Add Google Play Services, Play Store and any tested apps to the Magisk
   **DenyList**, and enable **Zygisk** + **Enforce DenyList**.
5. Reboot. Verify with `adb shell getprop ro.build.fingerprint`.

## Hard limits — what this cannot do

This changes reported **strings**, not the hardware trust chain:

- **Play Integrity `DEVICE` / `STRONG` verdicts** require hardware-backed key
  attestation rooted in Google's certificate chain. A QEMU VM cannot produce
  it. Only `MEETS_BASIC_INTEGRITY` (and, with a working PIF, sometimes
  `MEETS_DEVICE_INTEGRITY` on some forks/time windows) is achievable.
- **Key attestation / StrongBox / Titan M2 / Widevine L1** are absent.
- **Verified Boot** is really `orange` (self-signed private release keys). The
  cosmetic `green` string does not change the AVB signature or the attested
  boot state; anything that reads the attestation extension still sees orange.
- The fingerprint claims `:user/release-keys` (Google-signed) while the image is
  signed with private release keys — an intentional, unavoidable mismatch for
  signature/attestation-aware checks.

Use only on virtual devices you own for local testing and research.

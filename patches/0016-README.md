# Patch 0016 — Report `caiman` hardware identity (no boot repack, no root)

## What this solves

Before this patch, `ro.hardware` / `ro.boot.hardware` reported `virtio` — a
residual virtualization tell that **could not** be fixed by the runtime
resetprop approach used for the other identity strings:

- Overriding `ro.hardware` in `vendor_init` (early boot) makes `init` import a
  non-existent `init.caiman.rc` HAL service graph and **bootloops** the device.
- Overriding it from any post-boot daemon (Magisk-style `resetprop`) is blocked
  twice over on a `user`/enforcing build: init rejects re-setting an existing
  `ro.` property, and `system/sepolicy` `neverallow { domain -init }
  properties_device:file write` fails the build if a custom domain tries to
  write the property area directly.

This patch fixes it at the only layer where it is safe: **the boot-config value
that init derives `ro.hardware` from**, combined with renaming the HAL selector
targets so the derived value still resolves a real service graph.

## Mechanism (verified against lineage-23.2 `system/core`)

`init` sets `ro.hardware` from `androidboot.hardware` in `ExportKernelBootProps()`
at the very start of second-stage boot, *before* `LoadBootScripts()` expands
`import /vendor/etc/init/hw/init.${ro.hardware}.rc`. So if the boot-config value
is already `caiman`, `ro.hardware` is `caiman` from the first instant — no
re-set, no property-area write, no SELinux violation.

The catch is that three things key off `ro.hardware` and would break if the
target didn't exist:

| Selector | Consumer | Handling |
|---|---|---|
| `init.${ro.hardware}.rc` | `rootdir/init.rc` import | install `init.caiman.rc` (= `init.virtio.rc`) |
| `init.recovery.${ro.hardware}.rc` | recovery first-stage init | install `init.recovery.caiman.rc` |
| `fstab.${ro.hardware}` | `fs_mgr` `GetFstabPath()` normal boot | add `fstab.caiman` (= `gen_fstab_virtio`), incl. `vendor_ramdisk` |
| `ueventd.${ro.hardware}.rc` | `mainline` `ueventd.rc` import | no-op: no `ueventd.virtio.rc` exists today either |

### Changes (`device/virt/virtio-common`)

1. `BoardConfigCommon.mk`: `androidboot.hardware=virtio` → `caiman`.
2. `device-common.mk`: install `init.virtio.rc` **also** as `init.caiman.rc`;
   install `init.recovery.virtio.rc` **also** as `init.recovery.caiman.rc`; add
   `fstab.caiman` and `fstab.caiman.vendor_ramdisk` to `PRODUCT_PACKAGES`.
3. `configs/fstab/Android.bp`: add a `prebuilt_etc { name: "fstab.caiman" }`
   pointing at the existing `:gen_fstab_virtio` output (byte-identical).

Everything is **additive** — the `virtio`-named copies are kept. That guarantees:

- **No bootloop**: whatever init derives, a matching real file exists.
- **GSI stays intact**: the GSI boot path sets `androidboot.fstab_suffix=virtio.gsi.*`
  on the kernel cmdline. `fs_mgr`'s `GetFstabPath()` checks `fstab_suffix`
  *before* `hardware`, and `fs_mgr_get_boot_config()` reads bootconfig before
  cmdline for the *same* key — but `fstab_suffix` and `hardware` are different
  keys, so the GSI suffix still wins for the fstab and continues to resolve the
  untouched `fstab.virtio.gsi.*`.

## Why this beats the daemon/TE-domain idea

A `caiman` SELinux domain that mmaps `/dev/__properties__` to rewrite `ro.*`
(the Magisk `resetprop` technique) fails the build: `system/sepolicy`
`private/domain.te` has `neverallow { domain -init } properties_device:file
{ write ... }`. Only `init` may write the property area, and only at boot. This
patch works *with* that rule instead of carving a hole in it, so it needs no
sepolicy relaxation and produces no extra "this isn't stock" signal beyond the
identity string it is meant to change.

## Result

| Property | Before | After |
|---|---|---|
| `ro.hardware` | `virtio` | `caiman` |
| `ro.boot.hardware` | `virtio` | `caiman` |

`audit-fingerprint.sh` moves the `ro.hardware` row from **FLAG** to **PASS**.

## Residual limits (unchanged by this patch)

`ro.boot.verifiedbootstate` stays `orange` in the real AVB chain (only the
reported string can be cosmetically flipped); hardware key attestation,
StrongBox, and Play Integrity `DEVICE`/`STRONG` are still unattainable in a VM.
See `FINGERPRINT_DIFFERENCE_REFERENCE.md` §4 and §10.

## Build / verify

```shell
# CI (fork → Actions → Build). Local reset+patch is wired in:
patches/apply.sh <android-root>          # applies 0016 idempotently
scripts/verify-build-identity.sh <out>   # asserts init.caiman.rc + fstab.caiman
```

After flashing the new image, confirm on device:

```shell
adb shell getprop ro.hardware        # -> caiman
adb shell getprop ro.boot.hardware   # -> caiman
```

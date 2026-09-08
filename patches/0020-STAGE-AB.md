# Patches 0017–0020 — Per-app identity spoof (as built)

Status: **implemented**. This documents the mechanism that actually shipped,
which diverges from the original `0017-DESIGN.md` draft in one key way: the
spoofed property area is produced by **init (PID 1)**, not by a vendor
`spoofprop_gen` service. The vendor-domain approach was abandoned after three CI
failures on Treble/SELinux neverallows (a vendor domain may not mount, may not
read restricted `property_type` files, and may not read `/system`). init is
exempt from all three, so the generator moved there.

The goal is unchanged: **one physical VM, two identity views, decided per
process.** A target app (allowlisted in `spoof_policy.json`) sees a coherent
Pixel 9 Pro (caiman) identity; system processes and every non-listed app see the
real values. It must defend BOTH:

- **walk-A** — Java/libc reads: `Build.*`, `getprop`, `SystemProperties.get`,
  `__system_property_get` (bionic mmaps `/dev/__properties__`).
- **walk-B** — direct `open`+`read`/`mmap` of the `/dev/__properties__/u:object_r:*:s0`
  context files (issued via raw `svc` or a static native blob, bypassing libc).

## Patch layout

| Patch | Project | What it does |
|---|---|---|
| 0017 | `device/virt/virtio-common` | Ships spoof **data**: `configs/spoof/spoof_props.txt` (override key=value list) + `spoof_policy.json` (`{"packages":[…]}`), installed to `/system/etc/`. |
| 0018 | `system/core` | **Stage A**: `init/spoof_prop_area.cpp` builds a COMPLETE spoofed copy of the property area at `/dev/__properties_spoof__`, called from `PropertyInit()`. |
| 0019 | `device/virt/virt-common` | sepolicy: `file_contexts` label for the spoof dir + init create perms (`properties_device:dir`, `property_info:file`, `properties_serial:file`). |
| 0020 | `frameworks/base` | **Stage B**: zygote binds the spoof area over `/dev/__properties__` for target apps; `ProcessList` gates it from `spoof_policy.json` on any build type. |

## Stage A — init builds a complete, label-identical spoof area (patch 0018)

`BuildSpoofedPropertyArea()` runs once in `PropertyInit()` after
`PropertyLoadDerivedDefaults()`. It recursively copies `/dev/__properties__` →
`/dev/__properties_spoof__` (a tmpfs dir), and for each per-context file rewrites
the override values **in place** at the byte level:

- `prop_info` layout (validated offline against a real `build_prop` image):
  `sizeof==96`; `off 0` = atomic `uint32 serial` (`len = serial>>24`);
  `off 4` = `char value[92]` (`PROP_VALUE_MAX`, NUL-terminated);
  `off 96` = `char name[]` (NUL-terminated, variable).
- Each override key is located by scanning for `"\0<name>\0"` and backing up 96
  bytes; validated by `serial-len == strlen(value)` and `value[len]==NUL`; then
  value + serial length are rewritten. Record size and all trie offsets are
  untouched (only the value field changes), so the area stays structurally valid.

**SELinux labels are mirrored.** Each spoof file/dir is created with
`setfscreatecon()` set to the *source* file's `security.selinux` label
(`lgetfilecon`), so `/dev/__properties_spoof__/u:object_r:build_prop:s0` is born
labeled `build_prop`, the serial page `properties_serial`, the trie
`property_info`, etc. This is **required** for walk-B under Stage B: after the
bind mount the target app reads those files under the ordinary
`get_prop(domain, type)` allow rules, which only match if the file carries the
matching property-type label. A byte-only copy (all `properties_device`) would
be denied.

Everything is best-effort and non-fatal: any failure logs a warning and returns;
the real area and boot are never affected. Success is visible in logcat as
`spoof: built /dev/__properties_spoof__ with N overrides` and
`spoof: readback ro.product.model=Pixel 9 Pro`.

**Why init, not a vendor service** — init (PID 1) already holds
`allow init property_type:file { create … relabelto … }` and is excluded from
the `{ domain -init } properties_serial:file` / `property_type:file` neverallows.
0019 only adds the two remaining `dev_type` create perms (`property_info`,
`properties_serial`) plus `properties_device:dir` create/add_name, and a
`file_contexts` entry for the new dir. No new type, no new domain.

## Stage B — zygote binds the spoof area for target apps only (patch 0020)

Reuses AOSP's existing **appcompat sysprop-override** plumbing (added upstream
for per-app property overrides), which already threads a
`--bind-mount-sysprop-overrides` zygote arg end-to-end and calls
`BindMountSyspropOverride()` inside `SpecializeCommon` — *after*
`ensureInAppMountNamespace()` (the app is already in its private mount ns) and
*before* the SELinux domain transition.

Two changes:

1. **`com_android_internal_os_Zygote.cpp` — bind the complete spoof area.**
   `BindMountSyspropOverride()` now prefers `/dev/__properties_spoof__` as the
   bind source (falling back to the upstream `appcompat_override` subdir if the
   spoof area is absent, preserving stock behavior). It bind-mounts the whole
   spoof dir over `/dev/__properties__`, then calls
   `__system_properties_zygote_reload()` (drops the inherited real mmap,
   re-`Initialize`s the context nodes from the now-redirected path → walk-A sees
   spoof) and `ReloadBuildJavaConstants()` (re-derives `android.os.Build.*`).
   Because the bind is `MS_BIND|MS_REC` over the real dir in the app's *private*
   ns, walk-B (`open`/`mmap` of the per-context files) resolves to the spoof
   inodes too. System processes never enter this ns → real values.

   The upstream `mount_sysprop_overrides` block also calls `MountInitOverride()`,
   which mounts a tmpfs over `/system/etc/init` — that needs
   `allow zygote system_file:dir mounton`, which sepolicy grants **only** on
   userdebug/eng. Since our gate also fires on **user** builds, that call would
   fail and abort the target app during specialize (observed: `SIGSEGV`/`fail_fn`
   before the app runs). Identity spoofing does not need the init override, so
   `MountInitOverride()` is **not** called (its definition is retained,
   `[[maybe_unused]]`). Only the property-area bind runs.

2. **`ProcessList.java` — gate on the on-device policy, any build type.**
   Upstream only enables the override for userdebug/eng builds via a DeviceConfig
   package list. We add `isSpoofTargetPackage()`, which parses
   `/system/etc/spoof_policy.json` (`{"packages":[…]}`) once and caches it; if the
   launching package is listed, `bindOverrideSysprops` is set on **user** builds
   too. Empty/absent policy ⇒ feature entirely off.

## Coverage matrix (as built)

| Reader path | Covered | Mechanism |
|---|---|---|
| Java `SystemProperties.get` / `getprop` | ✅ | redirected mmap + `zygote_reload` |
| `Build.MODEL/FINGERPRINT/…` | ✅ | `ReloadBuildJavaConstants` after reload |
| libc `__system_property_get` | ✅ | reload re-maps to spoof area |
| **`svc` raw `open`+`mmap` of `/dev/__properties__/*`** | ✅ | kernel resolves path in app's mnt ns → spoof inode, label-matched |
| `getprop` in `shell` / other apps | ✅ (real) | not in policy ⇒ no bind ⇒ real area |
| system_server / all system procs | ✅ (real) | never enter the app ns |
| `/proc/self/mountinfo` self-inspection | ⚠️ | one bind row over `/dev/__properties__`; optional kernel filter (Stage D, patch pending) hides it |

## Honest limitations (unchanged)

- The bind mount is visible in `/proc/self/mountinfo` unless the optional kernel
  filter (Stage D) is added — a detection tell this technique introduces.
- Does **not** touch the hardware trust chain: AVB stays `orange`; key
  attestation / StrongBox / Play Integrity `DEVICE`+`STRONG` / Widevine L1 remain
  unattainable in a VM. This spoofs *observable identity strings/files*, not
  *attested* identity.
- `build.prop` **files** on disk (`/system/build.prop`, …) still hold the real
  build identity. Apps that parse those files directly (rather than the property
  area) are not covered by 0018/0020; covering them needs the per-app
  `build.prop` bind mounts from the original design (not yet built).
- The synthesized fingerprint tuple (`…/BP4A.251205.006/13749016:user/release-keys`)
  is internally coherent but is **not** a Google-published caiman OTA, so an
  online cross-check against Google's build list still shows "not a real
  published build".

## Build / verify

- Wired into `patches/apply.sh` (0019 on virt-common, 0017 on virtio-common,
  0018 on system/core, 0020 on frameworks/base); `build.sh` reset-list extended
  for `system/core` init files and the two `frameworks/base` files.
- `scripts/verify-build-identity.sh` asserts the spoof data files are staged and
  carry the coherent fingerprint tuple.
- Runtime (Stage A verified on release v2026.09.08): boots clean;
  `/dev/__properties_spoof__` exists with the 5 expected per-context files
  (EACCES to shell = present, dir is 0711); system view still reads real caiman.
  Stage B target-vs-system read comparison pending the 0020 CI build.

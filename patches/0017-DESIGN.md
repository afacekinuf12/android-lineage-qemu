# Patch 0017 (Design Draft) — Per-app property/fingerprint spoofing via mount-namespace redirection

Status: **implemented** as patches 0017–0020 (see `0020-STAGE-AB.md` for the
as-built mechanism, which differs from this draft in *where* the spoof area is
produced — init, not a vendor `spoofprop_gen` service — after the vendor-domain
approach hit Treble neverallows). This file is retained as the original
reviewable plan; the coverage matrix (§5) and honest limitations (§7) still hold.

---

## 1. Goal

Same physical VM, two views of identity, decided **per process**:

- **Target apps** (an allowlist) read *spoofed* values for a chosen set of
  read-only properties and fingerprint files (e.g. `ro.product.model`,
  `ro.build.fingerprint`, `ro.lineage.*`, `ro.hardware`).
- **System processes and every non-listed app** read the *real* values,
  unchanged.

Must survive the reader bypassing libc — i.e. an app that issues raw `svc`
syscalls or a statically linked native blob reading `/dev/__properties__` or
`/system/build.prop` directly must still see the spoofed view.

## 2. Why interception must be in the kernel VFS layer, not libc

`__system_property_get()` (bionic `system_property_api.cpp:86`) resolves to
`SystemProperties::Get()`, which walks a **`mmap(MAP_SHARED)`** of
`/dev/__properties__` (`prop_area.cpp:126`). Reading a property is therefore a
pure user-space memory access — **there is no per-read syscall to hook in the
kernel**, and a libc-level branch is trivially bypassed by `svc`/native.

The one thing that governs *all* readers uniformly — libc, `svc`, static
binaries, `getprop`, `Build.*` — is **path resolution**, which the kernel
performs against `task->nsproxy->mnt_ns`. If, inside the target app's mount
namespace, the path `/dev/__properties__` (and the `build.prop` files) resolve
to *spoofed* inodes, then every `open`/`mmap` of those paths — no matter how
issued — hits the fake data. An app cannot escape its own mount namespace
(`setns`/`mount` need `CAP_SYS_ADMIN`, which apps lack).

This is exactly why the redirection is robust against `svc` and native reads:
**`svc` bypasses libc, not the kernel's namespaced path lookup.**

## 3. Architecture

```
 build time
   └─ spoof_policy.json  (device/vendor overlay → /system/etc/spoof_policy.json)
        { "packages": ["com.foo.bar", ...],
          "properties": { "ro.hardware":"caiman", "ro.build.fingerprint":"google/caiman/...", ... },
          "buildprop_overrides": { "/system/build.prop": {...}, "/vendor/build.prop": {...} } }

 boot (init service, once)
   └─ spoofprop_gen:
        - clone real prop_area → write overridden keys → /dev/__properties_spoof__/  (tmpfs, ro to apps)
        - render spoofed copies of each build.prop → /dev/spoofprop/system.build.prop, ...

 app process launch (zygote specialize, per fork)
   ActivityManager/ProcessList (system_server)
     └─ decide: is target?  (packageName ∈ policy.packages)  → set Zygote arg  ZYGOTE_SPOOF_IDENTITY
   Zygote.nativeForkAndSpecialize → SpecializeCommon (native, already in private mnt ns)
     if arg set:
        ensureInAppMountNamespace()                 # already called for storage isolation
        bind-mount /dev/__properties_spoof__  →  /dev/__properties__
        bind-mount /dev/spoofprop/system.build.prop → /system/build.prop  (+ vendor/product ...)
        __system_properties_zygote_reload()         # drop inherited real mmap, re-open path → spoof
   → app code runs; every property/fingerprint read resolves to spoofed view
```

## 4. Concrete change set (per repo project → one patch each)

### 4.1 `device/virt/virtio-common` — policy + generator + sepolicy  (new files)
- `configs/spoof/spoof_policy.json` → installed to `/system/etc/spoof_policy.json`.
- `services/spoofprop_gen/` — small C++ init service:
  - reads the real prop area, applies `properties` overrides, writes a spoofed
    prop_area to a tmpfs at `/dev/__properties_spoof__`;
  - renders spoofed `build.prop` files to `/dev/spoofprop/`.
  - `init.virtio.rc` (already installed by this device) gains:
    `on post-fs-data … exec_start spoofprop_gen`.
- sepolicy (`sepolicy/vendor/`):
  - new type `spoofprop_file` for the tmpfs + rendered files; `spoofprop_gen`
    domain (`init_daemon_domain`) allowed to create/write them and read the
    real `properties_device`;
  - allow `zygote` to `mount`/`bind` `spoofprop_file` onto `properties_device`
    / `system_file` targets within its namespace (narrow `allow zygote
    spoofprop_file:{ file dir } { mounton … }`).

### 4.2 `frameworks/base` — decision + injection
- **Decision (Java, package name authoritative).** In `ProcessList`/`AMS`
  process-start path (or `ZygoteProcess.start`), look up the launching
  `packageName` against the parsed policy; if listed, OR a new flag
  `Zygote.SPOOF_IDENTITY` into the runtime flags (or add a dedicated
  `forkAndSpecialize` arg). Package name is not reliably available in native
  `SpecializeCommon`, so the *decision* is made here where it is authoritative;
  the *action* is done natively.
- **Injection (native, `com_android_internal_os_Zygote.cpp`).** In
  `SpecializeCommon` (anchor: after `ensureInAppMountNamespace` @1938 and after
  the `isolateAppData` block @1942–1950, before `SetSchedulerPolicy` @2030),
  when the spoof flag is set:
  1. `mount("/dev/__properties_spoof__", "/dev/__properties__", nullptr, MS_BIND|MS_REC, nullptr)`;
  2. bind-mount each spoofed `build.prop`;
  3. call `__system_properties_zygote_reload()` (bionic, `__INTRODUCED_IN(35)`,
     already exported in `libc.map.txt:1608`) to drop the inherited real mmap
     and re-open the now-redirected path.
- **`Build.*` needs no reflection:** `android/os/Build` is **not** in
  `config/preloaded-classes`, so its `static final` fields initialise in the
  forked app process *after* the bind-mount+reload → they read spoofed values
  naturally.

### 4.3 (optional) `0018` kernel patch — hide the redirection from `/proc/*/mountinfo`
The bind mounts are visible via `/proc/self/mountinfo` (readable by `svc`),
which is a **new** detection signal this technique introduces. If that matters,
a small kernel filter (`fs/proc_namespace.c` `show_mountinfo`) suppresses the
`spoofprop`/redirected rows for tasks whose `mnt_ns` is a spoof ns. This is the
*correct* place for a kernel change — filtering a `/proc` view — as opposed to
trying (and failing) to hook `__system_property_get`.

## 5. Coverage matrix

| Reader path | Covered | Mechanism |
|---|---|---|
| Java `SystemProperties.get` | ✅ | redirected mmap + `zygote_reload` |
| `Build.MODEL/DEVICE/...` | ✅ | not preloaded → initialises post-redirect |
| libc `__system_property_get` | ✅ | reload re-maps to spoof area |
| **`svc` raw `openat`+`mmap` of `/dev/__properties__`** | ✅ | kernel resolves path in app's mnt ns → spoof inode |
| **native read of `/system/build.prop`** | ✅ | per-app bind-mount of spoofed build.prop |
| `getprop` | ✅ | same libc path |
| `/proc/self/mountinfo` self-inspection | ⚠️ | needs optional 0018 kernel filter |

## 6. Interaction with 0016 (must decide)

0016 (merged) sets `ro.hardware=caiman` **globally**. The per-app model wants
"system sees real, target sees spoof". Two options:

- **Keep 0016**: `ro.hardware` stays globally `caiman`; 0017 spoofs only the
  other provenance (`ro.lineage.*`, fingerprint, model, `virtio_arm64only`).
- **Fold into 0017**: revert 0016's global effect (`ro.hardware` back to
  `virtio` globally) and move `caiman` into the per-app spoof set. This also
  drops the need for the `init.caiman.rc`/`fstab.caiman` copies.

Recommendation: **keep 0016** (already validated, low-risk) and let 0017 own the
`ro.lineage.*` / fingerprint / model deltas. Simpler and non-regressive.

## 7. Honest limitations (unchanged by 0017)

- Redirection is visible in `/proc/*/mountinfo` unless 0018 kernel filter is
  added; a determined app can also compare views across namespaces if it can
  reach another ns (it normally cannot).
- Does **not** touch the hardware trust chain: AVB stays `orange`; hardware key
  attestation, StrongBox, Play Integrity `DEVICE`/`STRONG`, Widevine L1 remain
  unattainable in a VM. This spoofs *observable identity strings/files*, not
  *attested* identity. Good for app compatibility / layout / anti-"is-this-a-VM"
  string checks; not for defeating hardware attestation.
- Per-app spoofing of `ro.*` that other **system** services already consumed at
  boot (e.g. anything cached in system_server) is irrelevant here — those are
  system processes and intentionally see the real value.

## 8. Open decisions (need product owner input before implementation)

1. **Scope of spoofed keys**: minimal (`ro.lineage.*` + `virtio_arm64only` +
   `jqssun`/`UNOFFICIAL`) or full (`+ Build.*`, `+ ro.build.fingerprint`,
   `+ ro.hardware`)?
2. **0016 handling**: keep global caiman (recommended) vs fold into per-app.
3. **Policy source**: static `/system/etc/spoof_policy.json` (needs rebuild to
   change) vs a small runtime-updatable service (adds a system service +
   sepolicy + update API).
4. **`/proc/mountinfo` hiding**: ship optional kernel patch 0018 or accept the
   mountinfo tell.

## 9. Build / verify plan (same pipeline as 0016)

- Patches land under `patches/0017-*.patch` (+ this design doc), wired into
  `patches/apply.sh`; `build.sh` reset-list extended for the touched projects.
- `scripts/verify-build-identity.sh` gains: `/system/etc/spoof_policy.json`
  present; `spoofprop_gen` binary + `.rc` staged; sepolicy types compiled.
- Runtime verification on the VM:
  - target app: `adb shell run-as <pkg> getprop ro.hardware` → spoof value;
  - a native probe app doing raw `openat("/dev/__properties__")` → spoof value;
  - `system_server`/`getprop` in `shell` (non-target) → real value;
  - `dumpsys` / Settings → unaffected.
- Push branch `feat/spoof-identity` → self-hosted Actions build → new release →
  import an isolated UTM instance → run the target-vs-system read comparison.

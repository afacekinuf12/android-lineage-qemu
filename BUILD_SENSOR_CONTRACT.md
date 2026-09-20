# Build Metadata and Sensor Contract

Source changes: 2026-09-14. These changes require a new Android build. They have
not been applied to the running StageB v0908 VM.

## Build Metadata

The StageB report contained a fingerprint with build ID `BP4A.260205.001` and
incremental `13561507`, but actual build properties contained `BP4A.251205.006`
and `20260908`. Patch 0007 supplied an unrelated fixed phone fingerprint while
Make/Soong generated the remaining metadata from the actual build.

Patch 0007 no longer overrides `BuildFingerprint`. Make's generated
`build_fingerprint-<target>.txt` now supplies the build fingerprint to Soong,
partition properties and existing AVB packaging logic. Its format is:

```text
<product-brand>/<actual-build-target>/<actual-device-target>:<platform-version>/<build-id>/<build-number>:<variant>/<tags>
```

The ARM64 build target remains `lineage_virtio_arm64only` with device target
`virtio_arm64only`. This deliberately identifies the project's software build,
not a Google OTA. Existing product aliases, SMBIOS values and functional
`ro.hardware`/init/fstab selectors are unchanged. Build ID, security patch,
signing keys and verified-boot state are not rewritten to match a phone.

`scripts/verify-product-contract.py` checks finalized staged properties:

- Fingerprints equal the generated build fingerprint, across installed partitions.
- ID, incremental, type and tags agree with each fingerprint's tokens.
- Release/codename agrees, including preview releases.
- Duplicate conflicting properties and unfinished `?=` assignments fail.
- Global ID, incremental and security patch agree where global metadata is emitted.
- Actual LineageOS target names are allowed; naming a virtual target is not an error.

The existing ARM64 identity/release-key verifier invokes this check. The x86_64
build invokes it with its own target name. Key/certificate verification is not
replaced by these metadata checks.

## Sensor Registration

`LOCAL_SENSOR_FILE_OVERRIDES=true` controls Cuttlefish's feature XML installation,
not the list returned by the default AIDL HAL. The old image still registered
nine example sensors, even though several corresponding features were omitted.

Patch 0008 now enables the product-scoped Soong boolean
`device_virt_virt_common.motion_sensors_only` and explicitly declares:

| HAL class | PackageManager feature | Host bridge |
|---|---|---|
| `AccelSensor` | `android.hardware.sensor.accelerometer` | `motion`, `rotate` |
| `GyroSensor` | `android.hardware.sensor.gyroscope` | `motion` |
| `MagnetometerSensor` | `android.hardware.sensor.compass` | `motion` |

Patch 0021 uses that boolean in `hardware/interfaces/sensors/aidl/default`.
It configures both the implementation library and service that consume the
inline constructor. For VirtIO builds, ambient temperature, pressure, light,
proximity, relative humidity and hinge angle are not registered. Without the
boolean, the upstream nine-sensor example list is unchanged.

Framework fusion sensors remain derived from the three motion sensors. Do not
assert that `SensorManager.TYPE_ALL` must return exactly three entries. Sensor
handles may change after rebuilding; the bridge resolves handles by type rather
than persisting numeric handles.

These remain virtual/test sensors, not physical Pixel sensor chips. Their
example vendor names, ranges and event behavior are not changed to copy a phone.
The existing HAL can generate example data in NORMAL mode and accepts bridge
data in DATA_INJECTION mode. A correct declaration set alone is not evidence
of physical sensor fidelity or live host input.

The product verifier parses all staged permission/sysconfig XML by feature
name rather than filename. Only the three motion features are accepted. This
finds stale declarations even when embedded in aggregate XML or another
partition; it also respects `unavailable-feature` when checking required motion
features. Suppressing an extra feature with `unavailable-feature` is not treated
as cleanup of the stale declaration.

## Incremental Builds and CI

`build.sh` restores only the two newly patched tracked HAL source files through
its existing patch preparation process. It removes the six obsolete generated
sensor XML files from vendor staging for the selected build targets. Soong
configuration/header changes trigger rebuilding the affected modules.

The `skip_checkout` workflow no longer overwrites patches and verifiers with
embedded Base64 snapshots. It requires the cached HEAD to match `GITHUB_SHA`
and tracked build inputs to be clean. A mismatch fails rather than silently
building old source; disable `skip_checkout` or prepare the intended checkout.
No workflow was dispatched, release published or key regenerated for this change.

On the Linux Android builder, use the normal build entry point:

```bash
BUILD_TARGET=arm64only ./build.sh
```

For an existing fully synchronized tree, `SKIP_REPO_SYNC=true` is supported by
that script. Do not use old `reuse_output` artifacts to claim a rebuilt sensor
HAL. Run the standalone staged checks with:

```bash
python3 scripts/verify-product-contract.py android/lineage/out/target/product/virtio_arm64only
bash scripts/verify-build-identity.sh android/lineage/out/target/product/virtio_arm64only
```

These validate staging, not the contents of an arbitrarily selected old ZIP.
Retain the exact generated image/archive and its hash for device verification.

## Verification Performed

- 43 Python tests passed, including 21 new product-contract/integration tests.
- Modified shell scripts pass `bash -n`; both workflow YAML files parse.
- Patches 0007 and 0008 apply to the locally cached device sources; the relevant
  series was checked alongside 0001/0006/0019. Cached virt-common already
  contained 0009; its reverse check confirmed that state.
- Existing 0016/0017 patches also apply to the cached virtio-common source.
- Patch 0021 applies to LineageOS `lineage-23.2` HAL files.
- `tests/check-motion-registration.py` compiled and executed the actual patched
  registration block with and without the boolean: three and nine classes,
  respectively. Both constructor consumers have matching Soong defaults.
- No full Android HAL compilation, image build, full remote patch-clone suite,
  deployment or live sensor-event test has been completed here.

Host regressions:

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/check-motion-registration.py /path/to/patched/hardware/interfaces
```

The network-backed CI patch suite (`tests/verify-patches.sh`) now includes 0021
and the compiled registration check. The local machine has no complete
`android/lineage` build tree, so no new boot/system/vendor images are claimed.

## Device Acceptance After Rebuild

1. Confirm the selected VM's build identity before installation. Use a new
   evidence directory and record hashes of the newly built images.
2. Compare `Build.FINGERPRINT`, ID and incremental plus per-partition properties
   with the staged build metadata. Do not accept the old hardcoded phone tuple.
3. Check both `SensorManager` enumeration and PackageManager features. The six
   excluded example sensor types must be absent; three motion types must exist.
   Derived framework fusion types are allowed.
4. Exercise each motion stream through the host bridge. Verify subscription,
   timestamps, units, rate and the behavior when no producer is connected.
5. Repeat the Inspector inode/JNI/isolation smoke test to catch unrelated
   regressions. An observation-count decrease after removing sensors is expected.

Existing per-app `spoof_props.txt` and the optional Magisk identity module are
separate legacy override paths and were not modified here. They may still
present fixed metadata to selected processes. Keep them out of the normal-build
acceptance baseline; this change does not claim consistency across those
overridden views. It also does not modify GPU, camera, memory or boot trust.

## Source References

- LineageOS `android_build`, `lineage-23.2`, `core/config.mk` and `core/sysprop.mk`.
- LineageOS `android_build_soong`, `lineage-23.2`, `scripts/gen_build_prop.py`.
- LineageOS `android_hardware_interfaces`, `lineage-23.2`, `sensors/aidl/default`.
- AOSP `device/google/cuttlefish`, `android-16.0.0_r4`,
  `shared/sensors/device_vendor.mk` and `guest/commands/sensor_injection/main.cpp`.

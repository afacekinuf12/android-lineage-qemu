#!/system/bin/sh
# Pixel 9 Pro (caiman) runtime identity for the LineageOS/QEMU research VM.
#
# post-fs-data runs before the framework starts, which is the correct phase to
# rewrite read-only (ro.*) properties. build.prop only covers a subset of these;
# ro.boot.* and ro.hardware are supplied by the bootloader/kernel cmdline and
# can only be corrected here with resetprop.
#
# This adjusts the reported identity string. It does NOT create a hardware trust
# chain: verified-boot state stays orange, and key/Play Integrity hardware
# attestation still reflects the virtual device.

MODDIR=${0%/*}

# --- Canonical caiman identity -------------------------------------------------
BRAND=google
MANUFACTURER=Google
MODEL="Pixel 9 Pro"
DEVICE=caiman
PRODUCT=caiman
BUILD_ID=BP4A.260205.001
INCREMENTAL=13561507
RELEASE=16
SECURITY_PATCH=2026-02-05
TAGS=release-keys
TYPE=user
FINGERPRINT="google/caiman/caiman:16/${BUILD_ID}/${INCREMENTAL}:user/release-keys"
DESCRIPTION="caiman-user 16 ${BUILD_ID} ${INCREMENTAL} release-keys"

# resetprop -n sets the value without triggering property-trigger side effects,
# which is safer for ro.* values consumed only as identity strings.
setprop_ro() {
    resetprop -n "$1" "$2"
}

# Per-partition product identity. Covering every partition prefix keeps the
# fingerprint self-consistent, which detectors check for.
for partition in "" system system_ext product vendor odm oem vendor_dlkm; do
    if [ -z "$partition" ]; then
        prefix="ro.product"
    else
        prefix="ro.product.${partition}"
    fi
    setprop_ro "${prefix}.brand" "$BRAND"
    setprop_ro "${prefix}.manufacturer" "$MANUFACTURER"
    setprop_ro "${prefix}.model" "$MODEL"
    setprop_ro "${prefix}.device" "$DEVICE"
    setprop_ro "${prefix}.name" "$PRODUCT"
done

# Per-partition build fingerprint and version metadata.
for prefix in ro.build ro.system.build ro.system_ext.build ro.product.build \
    ro.vendor.build ro.odm.build ro.bootimage.build ro.vendor_dlkm.build; do
    setprop_ro "${prefix}.fingerprint" "$FINGERPRINT"
done
setprop_ro ro.build.id "$BUILD_ID"
setprop_ro ro.build.display.id "$FINGERPRINT"
setprop_ro ro.build.description "$DESCRIPTION"
setprop_ro ro.build.flavor "caiman-user"
setprop_ro ro.build.product "$DEVICE"
setprop_ro ro.build.version.incremental "$INCREMENTAL"
setprop_ro ro.build.version.release "$RELEASE"
setprop_ro ro.build.version.release_or_codename "$RELEASE"
setprop_ro ro.build.version.security_patch "$SECURITY_PATCH"
setprop_ro ro.build.tags "$TAGS"
setprop_ro ro.build.type "$TYPE"
setprop_ro ro.vendor.build.security_patch "$SECURITY_PATCH"

# Boot / hardware identifiers. These come from the kernel cmdline and DMI, not
# build.prop, so they can only be corrected at runtime. We do NOT change them on
# the kernel cmdline itself, because init resolves HAL module paths from
# ro.hardware during early boot and a non-existent "caiman" HAL set would loop.
setprop_ro ro.hardware caiman
setprop_ro ro.boot.hardware caiman
setprop_ro ro.boot.hardware.sku caiman
setprop_ro ro.boot.product.hardware.sku caiman
setprop_ro ro.soc.manufacturer Google
setprop_ro ro.soc.model zumapro
setprop_ro ro.hardware.chipname zumapro

# SoC platform / board. Pixel 9 Pro (Tensor G4) reports the "zumapro" platform;
# leaving these unset or generic is a common emulator tell.
setprop_ro ro.board.platform zumapro
setprop_ro ro.product.board zumapro
setprop_ro ro.product.system.board caiman
setprop_ro ro.product.vendor.board caiman

# Boot mode / verified-boot cosmetic fields. The underlying verified-boot state
# stays orange; these only align the string values Android reports.
setprop_ro ro.boot.verifiedbootstate green
setprop_ro ro.boot.veritymode enforcing
setprop_ro ro.boot.flash.locked 1
setprop_ro ro.boot.vbmeta.device_state locked
setprop_ro vendor.boot.verifiedbootstate green
setprop_ro ro.boot.vbmeta.avb_version 1.3

# --- Scrub known emulator / QEMU marker properties -----------------------------
# The QEMU "virt" board does not create the classic goldfish/ranchu markers, but
# some tooling checks for them defensively. Delete any that leaked in so a
# property enumeration does not expose a virtualization signal.
for marker in \
    ro.kernel.qemu ro.kernel.qemu.gles ro.kernel.android.qemud \
    ro.boot.qemu ro.boot.qemu.gles \
    qemu.hw.mainkeys qemu.sf.fake_camera qemu.sf.lcd_density \
    init.svc.qemud init.svc.qemu-props \
    ro.hardware.gralloc.qemu; do
    resetprop --delete "$marker" 2>/dev/null
done

# A goldfish/ranchu-free hostname avoids the generic "localhost" emulator tell.
setprop_ro net.hostname android-caiman

exit 0

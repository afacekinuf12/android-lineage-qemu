#!/bin/bash

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Only the shell entry point is needed for the UI Automator regression.
ui_root="$WORK/uiautomator-wrapper"
ui_file="cmds/uiautomator/cmds/uiautomator/uiautomator.sh"
mkdir -p "$ui_root/$(dirname "$ui_file")"
curl -fLsS --retry 2 --max-time 60 \
  "https://raw.githubusercontent.com/LineageOS/android_frameworks_base/lineage-23.2/$ui_file" \
  -o "$ui_root/$ui_file"
git -C "$ui_root" init -q
git -C "$ui_root" apply "$ROOT/patches/0022-uiautomator-include-test-base-dependency.patch"
python3 "$ROOT/tests/check-uiautomator-wrapper.py" "$ui_root/$ui_file"

clone_and_check_series() {
  local repository=$1
  shift
  local checkout="$WORK/$repository"

  git clone --quiet --depth 1 --branch lineage-23.2 \
    "https://github.com/LineageOS/$repository.git" "$checkout"
  for patch in "$@"; do
    git -C "$checkout" apply --check "$ROOT/patches/$patch"
    git -C "$checkout" apply "$ROOT/patches/$patch"
  done
}

clone_and_check_aosp_series() {
  local repository=$1
  local revision=$2
  shift 2
  local checkout="$WORK/$repository"

  git clone --quiet --depth 1 --branch "$revision" \
    "https://android.googlesource.com/platform/external/${repository#android_external_}" \
    "$checkout"
  for patch in "$@"; do
    git -C "$checkout" apply --check "$ROOT/patches/$patch"
    git -C "$checkout" apply "$ROOT/patches/$patch"
  done
}

clone_and_check_series \
  android_device_virt_virt-common \
  0001-virt-common-enable-compat-hardware.patch \
  0006-virt-common-declare-bridged-gps.patch \
  0008-virt-common-align-declared-hardware.patch \
  0009-virt-common-pixel-platform-identity.patch \
  0023-virt-common-scope-lineage-settings-overlay.patch
clone_and_check_series \
  android_device_virt_virtio_arm64 \
  0002-virtio-arm64-expand-utm-hardware.patch \
  0005-virtio-arm64-use-compatible-utm-display.patch
clone_and_check_series \
  android_device_virt_virtio_arm64only \
  0007-virtio-arm64-consistent-product-identity.patch
clone_and_check_series \
  android_hardware_interfaces \
  0021-sensors-limit-virtio-to-bridged-motion.patch
clone_and_check_series android_device_virt_virtio-common
clone_and_check_series \
  android_external_mesa \
  0003-mesa-use-build-environment-python.patch \
  0011-mesa-report-mali-g715-identity.patch
clone_and_check_aosp_series \
  android_external_swiftshader android-16.0.0_r4 \
  0013-swiftshader-report-mali-g715-device-name.patch
clone_and_check_series \
  android_build_soong \
  0014-soong-stamp-build-date-in-utc.patch
clone_and_check_series \
  android_build \
  0015-build-make-stamp-vendor-date-in-utc.patch

mesa_checkout="$WORK/android_external_mesa"
grep -q 'return (const GLubyte \*) "ARM";' \
  "$mesa_checkout/src/mesa/main/getstring.c"
grep -q 'return (const GLubyte \*) "Mali-G715";' \
  "$mesa_checkout/src/mesa/main/getstring.c"
grep -q 'strcpy(p->deviceName, "Mali-G715");' \
  "$mesa_checkout/src/gallium/frontends/lavapipe/lvp_device.c"
grep -q 'snprintf(props->deviceName, sizeof(props->deviceName), "Mali-G715");' \
  "$mesa_checkout/src/virtio/vulkan/vn_physical_device.c"
grep -q 'strcpy(layer->api.deviceName, "Mali-G715");' \
  "$mesa_checkout/src/virtio/vulkan/vn_physical_device.c"
grep -q 'return "Mesa";' \
  "$mesa_checkout/src/gallium/drivers/llvmpipe/lp_screen.c"
grep -q 'VK_VENDOR_ID_MESA' \
  "$mesa_checkout/src/gallium/frontends/lavapipe/lvp_device.c"
if grep -q 'debug.angle.gl_\(vendor\|renderer\)' \
  "$WORK/android_device_virt_virt-common/configs/init/init.virt.rc"; then
  echo "ANGLE public string overrides would hide the real backend from Skia" >&2
  exit 1
fi
grep -q 'strcpy(properties.deviceName, "Mali-G715");' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkPhysicalDevice.cpp"
grep -q 'constexpr uint32_t VENDOR_ID = 0x1AE0;' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkConfig.hpp"
grep -q 'constexpr uint32_t DEVICE_ID = 0xC0DE;' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkConfig.hpp"
grep -q 'VK_DRIVER_ID_GOOGLE_SWIFTSHADER_KHR' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkPhysicalDevice.cpp"
grep -q 'strcpy(properties->driverName, "SwiftShader driver");' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkPhysicalDevice.cpp"
grep -q 'header->vendorID = VENDOR_ID;' \
  "$WORK/android_external_swiftshader/src/Vulkan/VkPipelineCache.cpp"
grep -q 'value ? "mesa" : "swiftshader"' \
  "$WORK/android_device_virt_virtio-common/services/virtgpu_detect/virtgpu_detect.c"
if grep -q 'value ? "mesa" : "mesa_swrast"' \
  "$WORK/android_device_virt_virtio-common/services/virtgpu_detect/virtgpu_detect.c"; then
  echo "virtgpu_detect unexpectedly defaults to Mesa software rendering" >&2
  exit 1
fi
grep -q 'services/virtgpu_detect/virtgpu_detect.c' "$ROOT/build.sh"
grep -q '"date", "-u", "-d", f"@{raw_date}"' \
  "$WORK/android_build_soong/scripts/gen_build_prop.py"
grep -q 'DATE_FROM_FILE := date -u -d @' \
  "$WORK/android_build/core/main.mk"

python3 "$ROOT/tests/check-motion-registration.py" \
  "$WORK/android_hardware_interfaces"
if grep -q 'BuildFingerprint=' \
  "$WORK/android_device_virt_virtio_arm64only/lineage_virtio_arm64only.mk"; then
  echo "Product must use the generated build fingerprint" >&2
  exit 1
fi
grep -q 'device_virt_virt_common,motion_sensors_only,true' \
  "$WORK/android_device_virt_virt-common/virt-common.mk"

echo "All LineageOS patches apply cleanly."

#!/bin/bash

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

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

clone_and_check_series \
  android_device_virt_virt-common \
  0001-virt-common-enable-compat-hardware.patch \
  0006-virt-common-declare-bridged-gps.patch \
  0008-virt-common-align-declared-hardware.patch \
  0009-virt-common-pixel-platform-identity.patch
clone_and_check_series \
  android_device_virt_virtio_arm64 \
  0002-virtio-arm64-expand-utm-hardware.patch \
  0005-virtio-arm64-use-compatible-utm-display.patch
clone_and_check_series \
  android_device_virt_virtio_arm64only \
  0007-virtio-arm64-consistent-product-identity.patch
clone_and_check_series \
  android_device_virt_virtio-common \
  0012-virtio-common-default-to-mesa-swrast.patch
clone_and_check_series \
  android_external_mesa \
  0003-mesa-use-build-environment-python.patch \
  0011-mesa-report-mali-g715-identity.patch

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
grep -q 'value ? "mesa" : "mesa_swrast"' \
  "$WORK/android_device_virt_virtio-common/services/virtgpu_detect/virtgpu_detect.c"

echo "All LineageOS patches apply cleanly."

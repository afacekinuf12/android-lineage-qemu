#!/bin/bash
# Hardware integration only, against a separately prepared AOSP VirtIO tree.
set -euo pipefail
android_root=${1:?usage: apply-aosp.sh ANDROID_ROOT}
patch_root=$(cd "$(dirname "$0")" && pwd)
[[ -d "$android_root/.repo" ]] || { echo "Missing Android repo checkout" >&2; exit 2; }

apply_series() {
  local project=$1 patch
  shift
  [[ -e "$android_root/$project/.git" ]] ||
    { echo "Missing project: $project" >&2; exit 2; }
  local patches=()
  for patch in "$@"; do patches+=("$patch_root/$patch"); done
  python3 "$patch_root/../scripts/apply-patch-series.py" \
    "$android_root/$project" "${patches[@]}"
}

apply_series device/virt/virt-common \
  0001-virt-common-enable-compat-hardware.patch \
  0006-virt-common-declare-bridged-gps.patch \
  0008-virt-common-align-declared-hardware.patch \
  0023-virt-common-scope-lineage-settings-overlay.patch
apply_series device/virt/virtio_arm64 \
  0002-virtio-arm64-expand-utm-hardware.patch \
  0005-virtio-arm64-use-compatible-utm-display.patch
apply_series external/mesa 0003-mesa-use-build-environment-python.patch
apply_series hardware/interfaces 0021-sensors-limit-virtio-to-bridged-motion.patch
apply_series frameworks/base 0022-uiautomator-include-test-base-dependency.patch
apply_series system/core 0024-aosp-init-virtio-boot-and-vendor-hook.patch
apply_series build/soong 0025-aosp-soong-allow-virtio-mesa-build.patch
apply_series external/gptfdisk 0026-aosp-gptfdisk-recovery-variants.patch
apply_series bootable/recovery 0027-aosp-recovery-keep-ethernet-up.patch

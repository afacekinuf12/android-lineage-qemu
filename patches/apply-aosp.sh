#!/bin/bash
# Hardware integration only, against a separately prepared AOSP VirtIO tree.
set -euo pipefail
android_root=${1:?usage: apply-aosp.sh ANDROID_ROOT}
patch_root=$(cd "$(dirname "$0")" && pwd)
[[ -d "$android_root/.repo" ]] || { echo "Missing Android repo checkout" >&2; exit 2; }

apply_one() {
  local project=$1 patch=$2
  [[ -e "$android_root/$project/.git" ]] ||
    { echo "Missing project: $project" >&2; exit 2; }
  if git -C "$android_root/$project" apply --reverse --check "$patch_root/$patch" 2>/dev/null; then
    return
  fi
  git -C "$android_root/$project" apply --check "$patch_root/$patch"
  git -C "$android_root/$project" apply "$patch_root/$patch"
}

apply_one device/virt/virt-common 0001-virt-common-enable-compat-hardware.patch
apply_one device/virt/virt-common 0006-virt-common-declare-bridged-gps.patch
apply_one device/virt/virt-common 0008-virt-common-align-declared-hardware.patch
apply_one device/virt/virt-common 0023-virt-common-scope-lineage-settings-overlay.patch
apply_one device/virt/virtio_arm64 0002-virtio-arm64-expand-utm-hardware.patch
apply_one device/virt/virtio_arm64 0005-virtio-arm64-use-compatible-utm-display.patch
apply_one external/mesa 0003-mesa-use-build-environment-python.patch
apply_one hardware/interfaces 0021-sensors-limit-virtio-to-bridged-motion.patch
apply_one frameworks/base 0022-uiautomator-include-test-base-dependency.patch
apply_one system/core 0024-aosp-init-virtio-boot-and-vendor-hook.patch
apply_one build/soong 0025-aosp-soong-allow-virtio-mesa-build.patch
apply_one external/gptfdisk 0026-aosp-gptfdisk-recovery-variants.patch

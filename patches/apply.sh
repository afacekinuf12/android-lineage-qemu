#!/bin/bash

set -euo pipefail

ANDROID_ROOT=${1:-}
PATCH_ROOT=$(cd "$(dirname "$0")" && pwd)

if [[ -z "$ANDROID_ROOT" || ! -d "$ANDROID_ROOT/.repo" ]]; then
  echo "usage: $0 <android-source-root>" >&2
  exit 2
fi

apply_patch() {
  local project=$1
  local patch=$2
  local project_dir="$ANDROID_ROOT/$project"
  local patch_file="$PATCH_ROOT/$patch"

  if [[ ! -d "$project_dir/.git" ]]; then
    echo "missing Android project: $project" >&2
    exit 1
  fi
  if git -C "$project_dir" apply --reverse --check "$patch_file" 2>/dev/null; then
    echo "already applied: $patch"
    return
  fi

  git -C "$project_dir" apply --check "$patch_file"
  git -C "$project_dir" apply "$patch_file"
  echo "applied: $patch"
}

apply_patch device/virt/virt-common 0001-virt-common-enable-compat-hardware.patch
apply_patch device/virt/virt-common 0006-virt-common-declare-bridged-gps.patch
apply_patch device/virt/virt-common 0008-virt-common-align-declared-hardware.patch
apply_patch device/virt/virt-common 0009-virt-common-pixel-platform-identity.patch
apply_patch device/virt/virtio_arm64 0002-virtio-arm64-expand-utm-hardware.patch
apply_patch device/virt/virtio_arm64 0005-virtio-arm64-use-compatible-utm-display.patch
apply_patch device/virt/virtio_arm64only 0007-virtio-arm64-consistent-product-identity.patch
apply_patch external/mesa 0003-mesa-use-build-environment-python.patch
apply_patch external/mesa 0011-mesa-report-mali-g715-identity.patch

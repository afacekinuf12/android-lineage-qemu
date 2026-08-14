#!/bin/bash

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

clone_and_check() {
  local repository=$1
  local patch=$2
  local checkout="$WORK/${repository}-${patch%.patch}"

  git clone --quiet --depth 1 --branch lineage-23.2 \
    "https://github.com/LineageOS/$repository.git" "$checkout"
  git -C "$checkout" apply --check "$ROOT/patches/$patch"
}

clone_and_check \
  android_device_virt_virt-common \
  0001-virt-common-enable-compat-hardware.patch
clone_and_check \
  android_device_virt_virtio_arm64 \
  0002-virtio-arm64-expand-utm-hardware.patch
clone_and_check \
  android_device_virt_virtio_arm64 \
  0004-virtio-arm64-increase-utm-memory.patch
clone_and_check \
  android_device_virt_virtio_arm64 \
  0005-virtio-arm64-use-compatible-utm-display.patch
clone_and_check \
  android_external_mesa \
  0003-mesa-use-build-environment-python.patch

echo "All LineageOS patches apply cleanly."

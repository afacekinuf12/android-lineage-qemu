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
  android_external_mesa \
  0003-mesa-use-build-environment-python.patch

echo "All LineageOS patches apply cleanly."

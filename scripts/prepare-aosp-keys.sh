#!/bin/bash
# Reuse the existing signing identity without loading a distribution product.
set -euo pipefail

android_root=${1:?usage: prepare-aosp-keys.sh ANDROID_ROOT}
key_store=${RELEASE_KEYS_DIR:-$HOME/.android-lineage-qemu-release-keys}
security="$android_root/build/make/target/product/security"
destination="$android_root/vendor/virtio_aosp/keys"
names=(releasekey platform shared media networkstack sdk_sandbox bluetooth nfc)

[[ -d "$security" ]] || { echo "Android security source directory missing" >&2; exit 2; }
# Complete validation before writing. A missing half of a key pair must never
# cause a replacement key to be generated or break signing continuity.
for name in "${names[@]}"; do
  [[ -s "$key_store/$name.pk8" && -s "$key_store/$name.x509.pem" ]] ||
    { echo "Missing signing pair: $name in RELEASE_KEYS_DIR" >&2; exit 2; }
done
for name in "${names[@]}"; do
  if [[ -e "$destination/$name.x509.pem" ]] &&
     ! cmp -s "$key_store/$name.x509.pem" "$destination/$name.x509.pem"; then
    echo "Refusing to change an already provisioned AOSP signing identity: $name" >&2
    exit 2
  fi
done
mkdir -p "$destination"
chmod 700 "$destination"
for name in "${names[@]}"; do
  install -m 600 "$key_store/$name.pk8" "$destination/$name.pk8"
  install -m 644 "$key_store/$name.x509.pem" "$destination/$name.x509.pem"
  standard_name=$name
  [[ "$name" != releasekey ]] || standard_name=testkey
  install -m 600 "$key_store/$name.pk8" "$security/$standard_name.pk8"
  install -m 644 "$key_store/$name.x509.pem" "$security/$standard_name.x509.pem"
done

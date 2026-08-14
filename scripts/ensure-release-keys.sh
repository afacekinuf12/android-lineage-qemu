#!/bin/bash

set -euo pipefail

ANDROID_ROOT=${1:-}
KEY_STORE=${RELEASE_KEYS_DIR:-$HOME/.android-lineage-qemu-release-keys}
KEY_NAMES=(releasekey platform shared media networkstack)
SUBJECT=${RELEASE_KEY_SUBJECT:-/C=US/O=OpenMobile/OU=Android/CN=OpenMobile Virtual Device}

if [[ -z "$ANDROID_ROOT" || ! -d "$ANDROID_ROOT/build/make/target/product/security" ]]; then
  echo "usage: $0 <android-source-root>" >&2
  exit 2
fi

mkdir -p "$KEY_STORE"
chmod 700 "$KEY_STORE"

for name in "${KEY_NAMES[@]}"; do
  if [[ ! -f "$KEY_STORE/$name.pk8" || ! -f "$KEY_STORE/$name.x509.pem" ]]; then
    rm -f "$KEY_STORE/$name.pk8" "$KEY_STORE/$name.x509.pem"
    if ! printf '\n' | "$ANDROID_ROOT/development/tools/make_key" \
      "$KEY_STORE/$name" "$SUBJECT"; then
      if [[ ! -f "$KEY_STORE/$name.pk8" ||
        ! -f "$KEY_STORE/$name.x509.pem" ]]; then
        echo "failed to generate release key: $name" >&2
        exit 1
      fi
    fi
  fi
done

private_keys="$ANDROID_ROOT/vendor/lineage-priv/keys"
mkdir -p "$private_keys"
chmod 700 "$private_keys"

for name in "${KEY_NAMES[@]}"; do
  cp "$KEY_STORE/$name.pk8" "$private_keys/$name.pk8"
  cp "$KEY_STORE/$name.x509.pem" "$private_keys/$name.x509.pem"
done

# Replace the standard development certificates so modules that explicitly use
# platform/shared/media/networkstack are not signed with public AOSP test keys.
security="$ANDROID_ROOT/build/make/target/product/security"
for name in platform shared media networkstack; do
  cp "$KEY_STORE/$name.pk8" "$security/$name.pk8"
  cp "$KEY_STORE/$name.x509.pem" "$security/$name.x509.pem"
done
cp "$KEY_STORE/releasekey.pk8" "$security/testkey.pk8"
cp "$KEY_STORE/releasekey.x509.pem" "$security/testkey.x509.pem"

cat > "$private_keys/keys.mk" <<'EOF'
PRODUCT_DEFAULT_DEV_CERTIFICATE := vendor/lineage-priv/keys/releasekey
EOF

find "$private_keys" -type f -name '*.pk8' -exec chmod 600 {} +
find "$private_keys" -type f -name '*.x509.pem' -exec chmod 644 {} +

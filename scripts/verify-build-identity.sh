#!/bin/bash

set -euo pipefail

PRODUCT_OUT=${1:-}
if [[ -z "$PRODUCT_OUT" || ! -d "$PRODUCT_OUT" ]]; then
  echo "usage: $0 <product-out>" >&2
  exit 2
fi

ANDROID_ROOT=$(cd "$PRODUCT_OUT/../../../.." && pwd)
KEY_STORE=${RELEASE_KEYS_DIR:-$HOME/.android-lineage-qemu-release-keys}
system_prop="$PRODUCT_OUT/system/build.prop"
vendor_prop="$PRODUCT_OUT/vendor/build.prop"
permissions="$PRODUCT_OUT/vendor/etc/permissions"
product_permissions="$PRODUCT_OUT/product/etc/permissions"
target_files="$PRODUCT_OUT/obj/PACKAGING/target_files_intermediates"
virtgpu_detect="$PRODUCT_OUT/vendor/bin/virtgpu_detect"

require_property() {
  local file=$1
  local pattern=$2
  local property_prefix=$3

  if ! grep -q "$pattern" "$file"; then
    echo "missing expected property in $file: $pattern" >&2
    grep "^$property_prefix" "$file" >&2 || true
    exit 1
  fi
}

require_property "$system_prop" '^ro.build.fingerprint=google/caiman/caiman:' \
  'ro.build.fingerprint='
require_property "$system_prop" ':user/release-keys$' 'ro.build.'
require_property "$system_prop" '^ro.product.system.brand=google$' \
  'ro.product.system.'
require_property "$system_prop" '^ro.product.system.manufacturer=Google$' \
  'ro.product.system.'
require_property "$system_prop" '^ro.product.system.model=Pixel 9 Pro$' \
  'ro.product.system.'
require_property "$vendor_prop" '^ro.product.vendor.device=caiman$' \
  'ro.product.vendor.'
require_property "$vendor_prop" '^ro.product.vendor.name=caiman$' \
  'ro.product.vendor.'
require_property "$vendor_prop" '^ro.soc.manufacturer=Google$' 'ro.soc.'
require_property "$vendor_prop" '^ro.soc.model=zumapro$' 'ro.soc.'

if grep -Eq 'liuming|n37-007-050|test-keys|eng\.' "$system_prop" "$vendor_prop"; then
  echo "build identity still exposes development metadata" >&2
  exit 1
fi

mapfile -t build_props < <(find "$PRODUCT_OUT" -name build.prop -type f)
if grep -Ehi \
  '^(ro\.product\..*\.(brand|manufacturer|model)|ro\..*build\.fingerprint)=' \
  "${build_props[@]}" |
  grep -Eqi '=(.*)(qemu|virtio|generic|ranchu|goldfish|emulator|virtual|openmobile)'; then
  echo "public build identity still exposes a virtualization identifier" >&2
  exit 1
fi

test -f "$permissions/android.hardware.sensor.gyroscope.xml"
test -f "$permissions/android.hardware.sensor.compass.xml"
test ! -f "$permissions/android.hardware.sensor.hinge_angle.xml"
test ! -f "$permissions/android.hardware.sensor.relative_humidity.xml"
test ! -f "$permissions/android.hardware.sensor.barometer.xml"
test ! -f "$product_permissions/android.hardware.type.pc.xml"
test -f "$PRODUCT_OUT/vendor/etc/init/hw/init.virtio.rc"
test ! -f "$PRODUCT_OUT/vendor/etc/init/hw/init.caiman.rc"

# UTM's non-3D VirtIO GPU must use the stable ANGLE/Pastel fallback. Guard the
# incremental runner against a stale binary from the reverted Mesa-swrast
# experiment, which would otherwise boot but silently select the wrong stack.
if [[ ! -x "$virtgpu_detect" ]] ||
  ! grep -aFq 'swiftshader' "$virtgpu_detect" ||
  grep -aFq 'mesa_swrast' "$virtgpu_detect"; then
  echo "virtgpu_detect does not select the expected SwiftShader fallback" >&2
  strings "$virtgpu_detect" 2>/dev/null |
    grep -xE 'mesa|mesa_swrast|swiftshader' >&2 || true
  exit 1
fi

misc_info=$(find "$target_files" -path '*/META/misc_info.txt' -type f | head -1)
grep -q '^default_system_dev_certificate=vendor/lineage-priv/keys/releasekey$' \
  "$misc_info"

for name in releasekey platform shared media networkstack sdk_sandbox bluetooth nfc; do
  private_certificate="$KEY_STORE/$name.x509.pem"
  if [[ "$name" == releasekey ]]; then
    build_certificate="$ANDROID_ROOT/build/make/target/product/security/testkey.x509.pem"
  else
    build_certificate="$ANDROID_ROOT/build/make/target/product/security/$name.x509.pem"
  fi

  cmp -s "$private_certificate" \
    "$ANDROID_ROOT/vendor/lineage-priv/keys/$name.x509.pem"
  cmp -s "$private_certificate" "$build_certificate"
done
cmp -s "$KEY_STORE/releasekey.x509.pem" \
  "$ANDROID_ROOT/vendor/lineage-priv/keys/testkey.x509.pem"

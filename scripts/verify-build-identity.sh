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
init_virt="$PRODUCT_OUT/vendor/etc/init/hw/init.virt.rc"

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

mapfile -t build_props < <(find "$PRODUCT_OUT" -name build.prop -type f)

# Reject build-host PII in any staged build.prop: developer usernames/hosts,
# the internal build host, absolute source paths, private network endpoints,
# and internal domains that identify where the image was produced.
if grep -Eqi \
  'liuming|n37-007-050|10\.37\.7\.50|\.byted\.org|bytedance|/data00|/home/[a-z]|/Users/[a-z]' \
  "${build_props[@]}"; then
  echo "build identity still exposes build-host metadata (user/host/path/network)" >&2
  grep -Eni 'liuming|n37-007-050|10\.37\.7\.50|\.byted\.org|bytedance|/data00|/home/[a-z]|/Users/[a-z]' \
    "${build_props[@]}" >&2 || true
  exit 1
fi

# Reject engineering builds and residual test-keys signing metadata.
if grep -Eq 'test-keys|eng\.' "$system_prop" "$vendor_prop"; then
  echo "build identity still exposes development metadata" >&2
  exit 1
fi

# ro.build.host / ro.build.user must be the neutral defaults, never a real
# developer account or workstation hostname.
if ! grep -q '^ro.build.host=buildhost$' "$system_prop"; then
  echo "ro.build.host is not the neutral 'buildhost' default" >&2
  grep '^ro.build.host=' "${build_props[@]}" >&2 || true
  exit 1
fi
if ! grep -q '^ro.build.user=android$' "$system_prop"; then
  echo "ro.build.user is not the neutral 'android' default" >&2
  grep '^ro.build.user=' "${build_props[@]}" >&2 || true
  exit 1
fi

# ro.*.build.date is stamped from the build host's clock; a non-UTC timezone
# abbreviation (e.g. CST) leaks the builder's locale. Require UTC.
if grep -Eh '^ro\..*build\.date=' "${build_props[@]}" |
  grep -Evq ' UTC | GMT '; then
  echo "build.date exposes a non-UTC build-host timezone" >&2
  grep -Eh '^ro\..*build\.date=' "${build_props[@]}" >&2 || true
  exit 1
fi

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
test -f "$init_virt"
# ro.hardware now reports "caiman" (patch 0016), so init expands
# init.${ro.hardware}.rc -> init.caiman.rc during early boot. That file MUST be
# staged or the guest bootloops when it cannot find its HAL service graph. The
# caiman-named fstab must likewise exist for normal-boot first-stage mount. Both
# are byte-identical to their virtio-named originals, which are retained.
test -f "$PRODUCT_OUT/vendor/etc/init/hw/init.caiman.rc"
cmp -s "$PRODUCT_OUT/vendor/etc/init/hw/init.virtio.rc" \
  "$PRODUCT_OUT/vendor/etc/init/hw/init.caiman.rc"
test -f "$PRODUCT_OUT/vendor/etc/fstab.caiman"
# Stage A identity spoof (patches 0017/0018/0019): the spoof data files must be
# staged, and init's spoof-area builder must be compiled in. init builds the
# spoofed property area at /dev/__properties_spoof__ at boot; this stage does
# not alter what system processes read.
test -f "$PRODUCT_OUT/system/etc/spoof_props.txt"
test -f "$PRODUCT_OUT/system/etc/spoof_policy.json"
# The spoof props must carry the coherent Pixel 9 Pro fingerprint tuple.
grep -q '^ro.build.fingerprint=google/caiman/caiman:16/BP4A.251205.006/13749016:user/release-keys$' \
  "$PRODUCT_OUT/system/etc/spoof_props.txt"
if grep -q 'debug.angle.gl_\(vendor\|renderer\)' "$init_virt"; then
  echo "unsafe global ANGLE identity override remains in $init_virt" >&2
  exit 1
fi

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

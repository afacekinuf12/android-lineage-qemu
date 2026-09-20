#!/bin/bash
# Build the standalone product in a separate AOSP + VirtIO source checkout.
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
android_root=${AOSP_SOURCE_ROOT:-}
fail() { echo "$*" >&2; exit 2; }
[[ -n "$android_root" && -d "$android_root/.repo" ]] ||
  fail "Set AOSP_SOURCE_ROOT to an AOSP checkout with the VirtIO device dependencies."
android_root=$(cd "$android_root" && pwd)
[[ "$android_root" != *[[:space:]]* ]] || fail "Android source path cannot contain whitespace."
[[ "${BUILD_TARGET:-arm64only}" == arm64only ]] || fail "AOSP profile currently supports arm64only."

# This runs before copying keys or patching source. A Lineage framework has
# direct SDK dependencies even if its product makefile is no longer inherited.
python3 "$root/scripts/verify-aosp-product.py" --source-root "$android_root"
if [[ "${1:-}" == --check ]]; then
  exit 0
fi
[[ $# == 0 ]] || fail "usage: build-aosp.sh [--check]"
[[ "$(uname -s)" == Linux ]] || fail "Full Android compilation requires Linux."
[[ -n "${AOSP_RELEASE_CONFIG:-}" ]] ||
  fail "Set AOSP_RELEASE_CONFIG to a release configuration supplied by this AOSP checkout."
[[ "$AOSP_RELEASE_CONFIG" =~ ^[a-zA-Z0-9_]+$ ]] || fail "Invalid release configuration."
[[ "${BUILD_JOBS:-8}" =~ ^[1-9][0-9]*$ ]] || fail "BUILD_JOBS must be positive."

bash "$root/patches/apply-aosp.sh" "$android_root"
mkdir -p "$android_root/vendor/virtio_aosp"
install -m 644 "$root/products/virtio_aosp/AndroidProducts.mk" \
  "$android_root/vendor/virtio_aosp/AndroidProducts.mk"
install -m 644 "$root/products/virtio_aosp/virtio_aosp_arm64.mk" \
  "$android_root/vendor/virtio_aosp/virtio_aosp_arm64.mk"
bash "$root/scripts/prepare-aosp-keys.sh" "$android_root"

# Never reuse the old Lineage staging directory or a different product's
# system_ext/product/vendor overlays.
mkdir -p "$android_root/out"
export OUT_DIR
OUT_DIR=$(mktemp -d "$android_root/out/virtio-aosp.XXXXXXXX")
export BUILD_USERNAME=android BUILD_HOSTNAME=buildhost TZ=UTC AB_OTA_UPDATER=false
export BUILD_NUMBER=${BUILD_NUMBER:-$(date -u '+%Y%m%d')}
unset LINEAGE_BUILD LINEAGE_VERSION LINEAGE_BUILDTYPE TARGET_PRODUCT TARGET_BUILD_VARIANT
unset TARGET_RELEASE TARGET_BUILD_APPS OUT_DIR_COMMON_BASE

cd "$android_root"
repo manifest -r -o "$OUT_DIR/resolved-manifest.xml"
# Android's envsetup scripts are not nounset-safe.
set +u
source build/envsetup.sh
lunch "virtio_aosp_arm64-${AOSP_RELEASE_CONFIG}-user"
[[ "$TARGET_PRODUCT" == virtio_aosp_arm64 && -z "${LINEAGE_BUILD:-}" ]] ||
  fail "The build environment selected an unexpected product."
kernel_dir=$(get_build_var TARGET_PREBUILT_KERNEL_DIR)
[[ -n "$kernel_dir" && -s "$kernel_dir/kernel" ]] ||
  fail "The selected product has no prebuilt kernel at $kernel_dir."
for module in btusb cfg80211 virt_wifi; do
  [[ -s "$kernel_dir/$module.ko" ]] ||
    fail "Missing selected kernel module: $kernel_dir/$module.ko"
done
m -j"${BUILD_JOBS:-8}" aapt2 vm-utm-zip otapackage
set -u

product_out="$OUT_DIR/target/product/virtio_arm64only"
python3 "$root/scripts/verify-aosp-product.py" \
  --product-out "$product_out" --aapt2 "$OUT_DIR/host/linux-x86/bin/aapt2" \
  > "$OUT_DIR/product-contract.json"

# Only this newly built and checked output can be exported.
shopt -s nullglob
utm=("$product_out"/VirtualMachine/UTM/UTM-VM*.zip)
ota=("$product_out"/*ota.zip)
[[ ${#utm[@]} == 1 && ${#ota[@]} == 1 ]] ||
  fail "Expected one fresh UTM archive and one OTA archive."
mkdir -p "$root/aosp-dist"
destination=$(mktemp -d "$root/aosp-dist/build.XXXXXXXX")
cp "${utm[@]}" "${ota[@]}" "$product_out/boot.img" "$product_out/recovery.img" "$destination/"
cp "$OUT_DIR/resolved-manifest.xml" "$OUT_DIR/product-contract.json" "$destination/"
(
  cd "$destination"
  sha256sum ./*.img ./*.zip ./resolved-manifest.xml ./product-contract.json > SHA256SUMS
)
echo "AOSP build artifacts: $destination"
echo "Runtime boot, hardware functionality and RiskDetector acceptance remain to be tested."

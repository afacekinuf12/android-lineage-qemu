#!/bin/bash

set -eo pipefail

export DEBIAN_FRONTEND=noninteractive
BUILD_TARGET=${BUILD_TARGET:-all}
BUILD_JOBS=${BUILD_JOBS:-16}
export BUILD_USERNAME=${BUILD_USERNAME:-android}
export BUILD_HOSTNAME=${BUILD_HOSTNAME:-buildhost}
export BUILD_NUMBER=${BUILD_NUMBER:-$(date -u '+%Y%m%d')}
export JAVA_TOOL_OPTIONS=${JAVA_TOOL_OPTIONS:--XX:+DisableAttachMechanism}
sudo apt update
sudo apt install -y sudo git android-sdk-platform-tools python3-packaging python3-yaml qemu-utils # libncurses5
if apt-cache show python-is-python3 >/dev/null 2>&1; then
  sudo apt install -y python-is-python3
elif ! command -v python >/dev/null 2>&1; then
  sudo ln -s /usr/bin/python3 /usr/local/bin/python
fi
sudo apt install -y bc bison build-essential ccache curl flex g++-multilib gcc-multilib git git-lfs gnupg gperf imagemagick ninja-build protobuf-compiler python3-protobuf lib32readline-dev lib32z1-dev libdw-dev libelf-dev lz4 libsdl1.2-dev libssl-dev libxml2 libxml2-utils lzop pngcrush rsync schedtool squashfs-tools xsltproc zip zlib1g-dev
if apt-cache show meson-1.5 >/dev/null 2>&1; then
  sudo apt install -y meson-1.5 glslang-tools python3-mako
else
  sudo apt install -y glslang-tools python3-mako python3-pip
  if ! python3 -m pip --version >/dev/null 2>&1; then
    sudo apt-get install --reinstall -y python3-pip
  fi
  python3 -m pip install --user 'meson==1.5.2'
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 8))'; then
  modern_python=
  for candidate in \
    "$HOME/miniconda3/bin/python3" \
    "$(command -v python3.12 2>/dev/null || true)" \
    "$(command -v python3.11 2>/dev/null || true)" \
    "$(command -v python3.10 2>/dev/null || true)" \
    "$(command -v python3.9 2>/dev/null || true)" \
    "$(command -v python3.8 2>/dev/null || true)"; do
    if [[ -n "$candidate" ]] &&
      "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 8))'; then
      modern_python=$candidate
      break
    fi
  done
  if [[ -z "$modern_python" ]]; then
    echo "LineageOS 23.2 requires Python 3.8 or newer." >&2
    exit 1
  fi

  python_env="$(realpath .)/.build-python"
  if [[ ! -x "$python_env/bin/python3" ]]; then
    "$modern_python" -m venv "$python_env"
  fi
  if ! "$python_env/bin/python3" -c 'import yaml, google.protobuf, mako, packaging' 2>/dev/null; then
    "$python_env/bin/python3" -m pip install PyYAML protobuf Mako packaging
  fi
  export PATH="$python_env/bin:$PATH"
fi
export LINEAGE_BUILD_PYTHON="$(dirname "$(command -v python3)")"

git config --global user.name "github-actions[bot]"
git config --global user.email "github-actions[bot]@users.noreply.github.com"
git config --global trailer.changeid.key "Change-Id"
git config --global color.ui true
git lfs install

unset REPO_URL
mkdir -p bin android/lineage
curl https://storage.googleapis.com/git-repo-downloads/repo > bin/repo
chmod a+x bin/repo
export PATH="$(realpath .)/bin:$PATH"
cd android/lineage
export PATH="$(realpath .)/prebuilts/sdk/tools/linux/bin/:$PATH"
repo init -u https://github.com/LineageOS/android.git -b lineage-23.2 --git-lfs --no-clone-bundle --depth 1
# Release keys are copied into standard certificate paths after sync. Restore
# those tracked files first so a later incremental sync starts from a clean tree.
if [[ -e build/make/.git ]]; then
  git -C build/make checkout -- \
    target/product/security/testkey.pk8 \
    target/product/security/testkey.x509.pem \
    target/product/security/platform.pk8 \
    target/product/security/platform.x509.pem \
    target/product/security/shared.pk8 \
    target/product/security/shared.x509.pem \
    target/product/security/media.pk8 \
    target/product/security/media.x509.pem \
    target/product/security/networkstack.pk8 \
    target/product/security/networkstack.x509.pem \
    target/product/security/sdk_sandbox.pk8 \
    target/product/security/sdk_sandbox.x509.pem \
    target/product/security/bluetooth.pk8 \
    target/product/security/bluetooth.x509.pem \
    target/product/security/nfc.pk8 \
    target/product/security/nfc.x509.pem
fi
sync_complete=false
for attempt in 1 2 3; do
  if [[ "$attempt" == 1 ]]; then
    sync_jobs=$(nproc)
  else
    sync_jobs=8
  fi
  if repo sync -c --prune --force-sync --retry-fetches=8 -j "$sync_jobs"; then
    sync_complete=true
    break
  fi
  sleep $((attempt * 60))
done
if [[ "$sync_complete" != true ]]; then
  echo "Failed to sync the Android source tree after three attempts." >&2
  exit 1
fi
sed -i 's/-$(LINEAGE_BUILDTYPE)/-jqssun/g' vendor/lineage/config/version.mk

../../scripts/ensure-release-keys.sh "$(pwd)"
source build/envsetup.sh
export AB_OTA_UPDATER=false ROOMSERVICE_BRANCHES="lineage-23.1 lineage-23.0"

# Let roomservice discover the ARM64 device trees before patching.
breakfast virtio_arm64only userdebug
git -C device/virt/virt-common checkout -- \
  configs/kernel/virt-common.config \
  configs/misc/grubenv.txt \
  virt-common.mk
git -C device/virt/virtio_arm64 checkout -- vm_templates/utm/config.plist
git -C device/virt/virtio_arm64only checkout -- lineage_virtio_arm64only.mk
git -C external/mesa checkout -- android/mesa3d_cross.mk
../../patches/apply.sh "$(pwd)"

if [[ "$BUILD_TARGET" == "all" || "$BUILD_TARGET" == "x86_64" ]]; then
  breakfast virtio_x86_64 userdebug
  m -j"$BUILD_JOBS" recoveryimage
  mv out/target/product/virtio_x86_64/recovery.img ../../recovery_x86_64-userdebug.img

  breakfast virtio_x86_64 user
  m -j"$BUILD_JOBS" vm-utm-zip otapackage
  mv out/target/product/virtio_x86_64/boot.img ../../boot_x86_64.img
  mv out/target/product/virtio_x86_64/recovery.img ../../recovery_x86_64.img
fi

if [[ "$BUILD_TARGET" == "all" || "$BUILD_TARGET" == "arm64only" ]]; then
  breakfast virtio_arm64only userdebug
  m -j"$BUILD_JOBS" recoveryimage
  mv out/target/product/virtio_arm64only/recovery.img ../../recovery_arm64only-userdebug.img

  breakfast virtio_arm64only user
  m -j"$BUILD_JOBS" vm-utm-zip otapackage
  ../../scripts/verify-build-identity.sh out/target/product/virtio_arm64only
  mv out/target/product/virtio_arm64only/boot.img ../../boot_arm64only.img
  mv out/target/product/virtio_arm64only/recovery.img ../../recovery_arm64only.img
fi

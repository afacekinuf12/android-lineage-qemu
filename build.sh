#!/bin/bash

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
BUILD_TARGET=${BUILD_TARGET:-all}
sudo apt update
sudo apt install -y sudo git android-sdk-platform-tools python3-yaml qemu-utils # libncurses5
if apt-cache show python-is-python3 >/dev/null 2>&1; then
  sudo apt install -y python-is-python3
elif ! command -v python >/dev/null 2>&1; then
  sudo ln -s /usr/bin/python3 /usr/local/bin/python
fi
sudo apt install -y bc bison build-essential ccache curl flex g++-multilib gcc-multilib git git-lfs gnupg gperf imagemagick protobuf-compiler python3-protobuf lib32readline-dev lib32z1-dev libdw-dev libelf-dev lz4 libsdl1.2-dev libssl-dev libxml2 libxml2-utils lzop pngcrush rsync schedtool squashfs-tools xsltproc zip zlib1g-dev
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

source build/envsetup.sh
export AB_OTA_UPDATER=false ROOMSERVICE_BRANCHES="lineage-23.1 lineage-23.0"

# Let roomservice discover the ARM64 device trees before patching.
breakfast virtio_arm64only userdebug
../../patches/apply.sh "$(pwd)"

if [[ "$BUILD_TARGET" == "all" || "$BUILD_TARGET" == "x86_64" ]]; then
  breakfast virtio_x86_64 userdebug
  m recoveryimage
  mv out/target/product/virtio_x86_64/recovery.img ../../recovery_x86_64-userdebug.img

  breakfast virtio_x86_64 user
  m vm-utm-zip otapackage
  mv out/target/product/virtio_x86_64/boot.img ../../boot_x86_64.img
  mv out/target/product/virtio_x86_64/recovery.img ../../recovery_x86_64.img
fi

if [[ "$BUILD_TARGET" == "all" || "$BUILD_TARGET" == "arm64only" ]]; then
  breakfast virtio_arm64only userdebug
  m recoveryimage
  mv out/target/product/virtio_arm64only/recovery.img ../../recovery_arm64only-userdebug.img

  breakfast virtio_arm64only user
  m vm-utm-zip otapackage
  mv out/target/product/virtio_arm64only/boot.img ../../boot_arm64only.img
  mv out/target/product/virtio_arm64only/recovery.img ../../recovery_arm64only.img
fi

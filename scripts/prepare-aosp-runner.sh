#!/bin/bash
# Prepare a separate, pinned AOSP checkout without changing the Lineage cache.
set -euo pipefail
control=$(cd "$(dirname "$0")/.." && pwd)
workspace=${GITHUB_WORKSPACE:?Run this from the dedicated AOSP workflow}
source_root="$workspace/android/aosp16-r4"
cache_root="$workspace/android/lineage"
state="$workspace/aosp-build-state"
mkdir -p "$state" "$state/bin" "$source_root"
exec > >(tee "$state/prepare.log") 2>&1

# Debian 10's system Python is too old for current repo and Android tooling.
for python_bin in "$workspace/.build-python/bin" "$HOME/miniconda3/bin"; do
  if [[ -x "$python_bin/python3" ]] &&
     "$python_bin/python3" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
    export PATH="$python_bin:$PATH"
    break
  fi
done
python3 -c 'import sys; print(sys.version); raise SystemExit(sys.version_info < (3, 9))'
python3 -B "$control/scripts/inspect-aosp-runner.py" "$state/runner-inspection.json"

[[ -d "$cache_root/.repo" ]] || { echo "Expected source cache is missing"; exit 2; }
[[ "$source_root" != "$cache_root" && ! -L "$source_root" ]] || exit 2
if [[ ! -x "$state/bin/repo" ]]; then
  install -m 755 "$cache_root/.repo/repo/repo" "$state/bin/repo"
fi
export PATH="$state/bin:$PATH"
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=http.proxy GIT_CONFIG_VALUE_0=
export GIT_CONFIG_KEY_1=https.proxy GIT_CONFIG_VALUE_1=
cd "$source_root"
if [[ -d .repo/manifests.git ]]; then
  manifest_url=$(git --git-dir=.repo/manifests.git config --get remote.origin.url)
  [[ "$manifest_url" == https://android.googlesource.com/platform/manifest ]] ||
    { echo "Refusing a non-AOSP source checkout"; exit 2; }
fi
repo init -u https://android.googlesource.com/platform/manifest \
  -b android-16.0.0_r4 --depth=1 --no-clone-bundle --git-lfs \
  --reference="$cache_root"
mkdir -p .repo/local_manifests
install -m 644 "$control/products/virtio_aosp/local_manifest.xml" \
  .repo/local_manifests/virtio.xml

# Repeated runs continue only this dedicated tree. Never force-reset the cache.
synced=false
for attempt in 1 2 3; do
  echo "AOSP source sync attempt $attempt"
  python3 -B "$control/scripts/repair-incomplete-aosp-fetches.py" "$source_root"
  if repo sync -c --no-clone-bundle --no-tags --retry-fetches=3 -j8; then
    synced=true
    break
  fi
done
[[ "$synced" == true ]] || { echo "AOSP sync incomplete; source retained for retry"; exit 1; }
repo manifest -r -o "$state/resolved-source-manifest.xml"
{
  echo "AOSP_SOURCE_ROOT=$source_root"
  echo "AOSP_SOURCE_REVISION=android-16.0.0_r4"
  echo "CONTROL_REVISION=$(git -C "$control" rev-parse HEAD)"
  echo "Source ready; kernel and full image build remain."
} | tee "$state/source-ready.txt"

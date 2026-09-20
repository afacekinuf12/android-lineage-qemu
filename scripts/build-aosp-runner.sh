#!/bin/bash
# Build only the independent tree completed by prepare-aosp-runner.sh.
set -euo pipefail
control=$(cd "$(dirname "$0")/.." && pwd)
workspace=${GITHUB_WORKSPACE:?Run this from the dedicated AOSP workflow}
state="$workspace/aosp-build-state"
export AOSP_SOURCE_ROOT="$workspace/android/aosp16-r4"
[[ -s "$state/source-ready.txt" && -d "$AOSP_SOURCE_ROOT/.repo" ]] ||
  { echo "Complete prepare-aosp before building"; exit 2; }
exec > >(tee "$state/build.log") 2>&1
for python_bin in "$workspace/.build-python/bin" "$HOME/miniconda3/bin"; do
  if [[ -x "$python_bin/python3" ]] &&
     "$python_bin/python3" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
    export PATH="$python_bin:$PATH"
    break
  fi
done
export PATH="$state/bin:$HOME/.local/bin:$AOSP_SOURCE_ROOT/prebuilts/sdk/tools/linux/bin:$PATH"
export LINEAGE_BUILD_PYTHON
LINEAGE_BUILD_PYTHON=$(dirname "$(command -v python3)")
python3 -c 'import yaml, google.protobuf, mako, packaging'
python3 -B "$control/scripts/stage-aosp-kernel.py" \
  "$workspace/android/lineage" "$AOSP_SOURCE_ROOT" "$state/kernel-provenance.json"
export AOSP_RELEASE_CONFIG=bp2a BUILD_TARGET=arm64only BUILD_JOBS=24
export RELEASE_KEYS_DIR="$HOME/.android-lineage-qemu-release-keys"
export AOSP_BUILD_STATE_DIR="$state"
export JAVA_TOOL_OPTIONS=-XX:+DisableAttachMechanism
bash "$control/build-aosp.sh"

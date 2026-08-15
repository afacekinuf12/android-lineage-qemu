#!/bin/bash

set -euo pipefail

serial=
output=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      serial=${2:-}
      shift 2
      ;;
    -h|--help)
      echo "usage: $0 --serial SERIAL OUTPUT_DIR"
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [[ -n "$output" ]]; then
        echo "only one output directory may be specified" >&2
        exit 2
      fi
      output=$1
      shift
      ;;
  esac
done

if [[ -z "$serial" || -z "$output" ]]; then
  echo "usage: $0 --serial SERIAL OUTPUT_DIR" >&2
  exit 2
fi
if [[ -e "$output" ]]; then
  echo "output already exists: $output" >&2
  exit 1
fi

mkdir -p "$output"
adb_command=(adb -s "$serial")

"${adb_command[@]}" wait-for-device

capture() {
  local name=$1
  shift
  {
    printf '# command:'
    printf ' %q' "$@"
    printf '\n'
    "${adb_command[@]}" shell "$@" 2>&1 || true
  } | tr -d '\r' >"$output/$name"
}

{
  echo "# Selected non-unique Android properties"
  "${adb_command[@]}" shell getprop |
    tr -d '\r' |
    grep -E '^\[(ro\.(product|build|system\.build|vendor\.build|odm\.build|product\.build|system_ext\.build|soc|hardware|board|zygote|opengles|surface_flinger|sf\.lcd_density|crypto)|ro\.boot\.(verifiedbootstate|vbmeta\.device_state|flash\.locked|avb_version))' |
    grep -Evi '(serial|imei|meid|mac|address|subscriber|hostname)' |
    LC_ALL=C sort
} >"$output/properties.txt"

capture features.txt pm list features
capture display.txt dumpsys display
capture sensors.txt dumpsys sensorservice
capture cameras.txt dumpsys media.camera
capture battery.txt dumpsys battery
capture graphics.txt dumpsys SurfaceFlinger
capture media_codecs.txt dumpsys media.codec

{
  echo "captured_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "collector_version=1"
  echo "serial_redacted=true"
} >"$output/metadata.txt"

echo "Profile written to $output"

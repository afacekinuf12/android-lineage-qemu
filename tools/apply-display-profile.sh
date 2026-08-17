#!/bin/bash

set -euo pipefail

serial=
reset=false
profile=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial)
      serial=${2:-}
      shift 2
      ;;
    --reset)
      reset=true
      shift
      ;;
    -h|--help)
      echo "usage: $0 --serial SERIAL [--reset] [pixel-9-pro-compat]"
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      exit 2
      ;;
    *)
      if [[ -n "$profile" ]]; then
        echo "only one profile may be specified" >&2
        exit 2
      fi
      profile=$1
      shift
      ;;
  esac
done

if [[ -z "$serial" ]]; then
  echo "usage: $0 --serial SERIAL [--reset] [pixel-9-pro-compat]" >&2
  exit 2
fi
if [[ "$reset" == false && "$profile" != "pixel-9-pro-compat" ]]; then
  echo "supported profile: pixel-9-pro-compat" >&2
  exit 2
fi
if [[ "$reset" == true && -n "$profile" ]]; then
  echo "--reset cannot be combined with a profile" >&2
  exit 2
fi

adb_command=("${ADB:-adb}" -s "$serial")
"${adb_command[@]}" wait-for-device

if [[ "$reset" == true ]]; then
  "${adb_command[@]}" shell wm size reset
  "${adb_command[@]}" shell wm density reset
else
  "${adb_command[@]}" shell wm size 1280x2856
  "${adb_command[@]}" shell wm density 495
fi

"${adb_command[@]}" shell wm size
"${adb_command[@]}" shell wm density

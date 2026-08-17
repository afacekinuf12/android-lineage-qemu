#!/bin/bash
#
# audit-fingerprint.sh — probe a running VM for Android emulator-detection
# signals and report each vector as PASS (looks like a real device) or FLAG
# (exposes a virtualization tell). This is the repeatable "逐项对比" companion to
# PIXEL_9_PRO_DIFFERENCE_REPORT.md; it inspects runtime state that source
# configuration alone cannot prove.
#
# Vectors are drawn from public emulator-detection projects (strazzere/
# anti-emulator, samohyes/Anti-vm-in-android, and common build.prop checks).
#
# Usage:
#   ADB=/opt/homebrew/bin/adb tools/audit-fingerprint.sh --serial 127.0.0.1:5555
#
set -uo pipefail

ADB=${ADB:-adb}
SERIAL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) SERIAL=$2; shift 2;;
    --adb) ADB=$2; shift 2;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done

adb_shell() {
  if [[ -n "$SERIAL" ]]; then
    "$ADB" -s "$SERIAL" shell "$@"
  else
    "$ADB" shell "$@"
  fi
}

if ! adb_shell true 2>/dev/null; then
  echo "cannot reach device over ADB (serial='${SERIAL:-<default>}')." >&2
  echo "boot the VM and authorize ADB, then re-run." >&2
  exit 1
fi

pass=0
flag=0
report() { # $1=PASS|FLAG $2=vector $3=detail
  printf '%-5s %-28s %s\n' "$1" "$2" "$3"
  [[ "$1" == PASS ]] && pass=$((pass + 1)) || flag=$((flag + 1))
}

getprop() { adb_shell getprop "$1" 2>/dev/null | tr -d '\r'; }

# 1. Build identity strings.
for prop in ro.product.brand ro.product.manufacturer ro.product.model \
  ro.product.device ro.product.name ro.build.fingerprint ro.hardware \
  ro.product.board ro.board.platform ro.serialno ro.bootloader; do
  value=$(getprop "$prop")
  if echo "$value" | grep -Eqi 'qemu|virtio|generic|ranchu|goldfish|emulator|unknown|sdk|vbox'; then
    report FLAG "$prop" "exposes '$value'"
  else
    report PASS "$prop" "$value"
  fi
done

# 2. QEMU marker properties (should be empty on a clean device).
for prop in ro.kernel.qemu ro.boot.qemu qemu.hw.mainkeys init.svc.qemud \
  init.svc.qemu-props ro.kernel.qemu.gles; do
  value=$(getprop "$prop")
  if [[ -n "$value" ]]; then
    report FLAG "$prop" "present: '$value'"
  else
    report PASS "$prop" "absent"
  fi
done

# 3. Emulator file nodes.
for node in /dev/socket/qemud /dev/qemu_pipe /system/lib/libc_malloc_debug_qemu.so \
  /sys/qemu_trace /system/bin/qemu-props /dev/socket/genyd; do
  if adb_shell "[ -e $node ]" 2>/dev/null; then
    report FLAG "file:$node" "exists"
  else
    report PASS "file:$node" "absent"
  fi
done

# 4. /proc/tty/drivers and /proc/cpuinfo markers.
if adb_shell "cat /proc/tty/drivers 2>/dev/null" | grep -qi goldfish; then
  report FLAG "/proc/tty/drivers" "goldfish driver present"
else
  report PASS "/proc/tty/drivers" "no goldfish driver"
fi
cpu=$(adb_shell "cat /proc/cpuinfo 2>/dev/null" | grep -i -m1 'model name\|Hardware')
if echo "$cpu" | grep -Eqi 'intel|amd|goldfish|ranchu'; then
  report FLAG "/proc/cpuinfo" "$cpu"
else
  report PASS "/proc/cpuinfo" "${cpu:-arm64, no x86/goldfish marker}"
fi

# 5. GL renderer string.
gl=$(getprop ro.hardware.egl)
if echo "$gl" | grep -Eqi 'swiftshader|emulation|android_emu'; then
  report FLAG "ro.hardware.egl" "software/emulated: '$gl'"
else
  report PASS "ro.hardware.egl" "${gl:-<unset>}"
fi

# 6. Sensors present.
sensors=$(adb_shell "dumpsys sensorservice 2>/dev/null | grep -c 'Sensor '" | tr -d '\r')
if [[ "${sensors:-0}" -ge 3 ]]; then
  report PASS "sensors" "$sensors sensors registered"
else
  report FLAG "sensors" "only ${sensors:-0} sensors"
fi

# 7. Verified-boot reported state.
vbs=$(getprop ro.boot.verifiedbootstate)
if [[ "$vbs" == green ]]; then
  report PASS "verifiedbootstate" "green (string; real AVB may differ)"
else
  report FLAG "verifiedbootstate" "${vbs:-<unset>}"
fi

# 8. Network MAC (fixed emulator default is a tell).
mac=$(adb_shell "cat /sys/class/net/*/address 2>/dev/null" | grep -iv '00:00:00:00:00:00' | head -1 | tr -d '\r')
if [[ "$mac" == "02:00:00:00:00:00" ]]; then
  report FLAG "mac" "fixed emulator MAC"
else
  report PASS "mac" "${mac:-<none>}"
fi

echo
echo "Summary: $pass PASS, $flag FLAG"
echo "Note: hardware attestation (Play Integrity DEVICE/STRONG, key attestation,"
echo "Widevine L1) cannot be satisfied by a VM and is out of scope for this audit."
[[ "$flag" -eq 0 ]]

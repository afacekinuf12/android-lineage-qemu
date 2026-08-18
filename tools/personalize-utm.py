#!/usr/bin/env python3

import argparse
import plistlib
import re
import secrets
import shutil
import subprocess
import uuid
from pathlib import Path


HARDWARE_PROFILES = {
    "pixel-9-pro-compat": {
        "cpu_count": 8,
        # Aspirational memory matching a real Pixel 9 Pro (16 GiB). This is a
        # ceiling, not a literal setting: apply_memory() caps it to a safe
        # share of host RAM so the guest never starves the macOS host.
        "memory_mib_max": 16384,
        "dynamic_resolution": False,
        # ro.bootloader value. Must be space-free because UTM re-splits each
        # AdditionalArguments array element on whitespace. The authoritative
        # human-readable value is re-asserted by the resetprop module at boot.
        "bootloader_version": "ripcurrentpro-1.5-13561507",
    }
}


def host_memory_mib() -> int:
    """Return host physical memory in MiB, or 0 if it cannot be determined."""
    sysctl = shutil.which("sysctl")
    if not sysctl:
        return 0
    try:
        out = subprocess.run(
            [sysctl, "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int(out.stdout.strip()) // (1024 * 1024)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0


def safe_memory_mib(requested_mib: int, host_mib: int) -> int:
    """Cap the requested guest memory to a safe share of host RAM.

    Reserve headroom for macOS and UTM/QEMU itself: never hand the guest more
    than ~55% of host RAM, and always leave at least 6 GiB for the host. When
    host memory is unknown (host_mib == 0) the request is returned unchanged.
    """
    if host_mib <= 0:
        return requested_mib
    share_cap = int(host_mib * 0.55)
    headroom_cap = host_mib - 6144
    cap = max(min(share_cap, headroom_cap), 2048)
    return min(requested_mib, cap)


def locally_administered_mac() -> str:
    octets = bytearray(secrets.token_bytes(6))
    octets[0] = (octets[0] | 0x02) & 0xFE
    return ":".join(f"{octet:02X}" for octet in octets)


def unique_serial() -> str:
    """Return a stable, device-unique serial number.

    QEMU exposes this as the SMBIOS type 1 serial, which Android's init reads
    from the DMI ``product_serial`` node and maps to ``ro.serialno``. Pixel
    serials are uppercase alphanumeric with no separators, so the generated
    value follows that shape rather than the earlier ``OM`` prefix.
    """
    return secrets.token_hex(7).upper()


def smbios_arguments(serial: str, bootloader_version: str) -> list:
    """Build the Pixel-compatible SMBIOS override arguments.

    - type 0 ``version`` -> DMI ``bios_version`` -> ``ro.bootloader``
    - type 1 ``manufacturer``/``product`` -> ``ro.product.*`` DMI overrides so
      LineageOS libinit does not fall back to QEMU defaults
    - type 1 ``serial`` -> DMI ``product_serial`` -> ``ro.serialno``
    - type 3 ``manufacturer`` -> chassis vendor

    Values must stay space-free: UTM splits every AdditionalArguments element
    on whitespace, so the codename ``caiman`` is used here while the display
    model ``Pixel 9 Pro`` is set through build.prop and the resetprop module.
    """
    return [
        "-smbios",
        f"type=0,vendor=Google,version={bootloader_version}",
        "-smbios",
        f"type=1,manufacturer=Google,product=caiman,serial={serial}",
        "-smbios",
        "type=3,manufacturer=Google",
    ]


def existing_serial(arguments: list) -> str:
    for argument in arguments:
        match = re.search(r"type=1,[^ ]*serial=([^,\s]+)", str(argument))
        if match:
            return match.group(1)
    return ""


def is_managed_smbios_value(argument: str) -> bool:
    return bool(re.match(r"type=[013](,|$)", str(argument)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assign unique local identity to an extracted UTM VM."
    )
    parser.add_argument("vm", type=Path, help="path to the .utm bundle")
    parser.add_argument("--name", default="Pixel 9 Pro")
    parser.add_argument(
        "--preserve-identity",
        action="store_true",
        help="do not change the existing UUID, name, or MAC addresses",
    )
    parser.add_argument(
        "--hardware-profile",
        choices=HARDWARE_PROFILES,
        help="apply a resource and display compatibility profile",
    )
    parser.add_argument(
        "--memory-mib",
        type=int,
        default=None,
        help="override guest memory (MiB); still capped to a safe share of "
        "host RAM unless --allow-oversized-memory is given",
    )
    parser.add_argument(
        "--allow-oversized-memory",
        action="store_true",
        help="skip the host-RAM safety cap (use only if you know the host "
        "has memory to spare)",
    )
    args = parser.parse_args()

    config_path = args.vm / "config.plist"
    with config_path.open("rb") as source:
        config = plistlib.load(source)

    if not args.preserve_identity:
        config["Information"]["UUID"] = str(uuid.uuid4()).upper()
        config["Information"]["Name"] = args.name
        for network in config.get("Network", []):
            network["MacAddress"] = locally_administered_mac()
    if args.hardware_profile:
        profile = HARDWARE_PROFILES[args.hardware_profile]
        config["System"]["CPUCount"] = profile["cpu_count"]
        requested = args.memory_mib or profile["memory_mib_max"]
        if args.allow_oversized_memory:
            memory = requested
        else:
            memory = safe_memory_mib(requested, host_memory_mib())
        config["System"]["MemorySize"] = memory
        for display in config.get("Display", []):
            display["DynamicResolution"] = profile["dynamic_resolution"]
        arguments = config["QEMU"].setdefault("AdditionalArguments", [])
        # Reuse the existing serial when preserving identity (e.g. re-applying the
        # profile to a running instance); otherwise assign a fresh unique serial.
        serial = existing_serial(arguments) if args.preserve_identity else ""
        if not serial:
            serial = unique_serial()
        managed = smbios_arguments(serial, profile["bootloader_version"])
        # Drop any previously managed SMBIOS pairs, then append the current set.
        rebuilt = []
        index = 0
        while index < len(arguments):
            token = str(arguments[index])
            if token == "-smbios" and index + 1 < len(arguments) and is_managed_smbios_value(arguments[index + 1]):
                index += 2
                continue
            rebuilt.append(arguments[index])
            index += 1
        rebuilt.extend(managed)
        arguments[:] = rebuilt

    with config_path.open("wb") as destination:
        plistlib.dump(config, destination, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

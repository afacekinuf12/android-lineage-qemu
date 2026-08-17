#!/usr/bin/env python3

import argparse
import plistlib
import re
import secrets
import uuid
from pathlib import Path


HARDWARE_PROFILES = {
    "pixel-9-pro-compat": {
        "cpu_count": 8,
        "memory_mib": 16384,
        "dynamic_resolution": False,
        "bootloader_version": "OpenMobile-1.0",
    }
}


def locally_administered_mac() -> str:
    octets = bytearray(secrets.token_bytes(6))
    octets[0] = (octets[0] | 0x02) & 0xFE
    return ":".join(f"{octet:02X}" for octet in octets)


def unique_serial() -> str:
    """Return a stable, device-unique serial number.

    QEMU exposes this as the SMBIOS type 1 serial, which Android's init reads
    from the DMI ``product_serial`` node and maps to ``ro.serialno``.
    """
    return "OM" + secrets.token_hex(7).upper()


def smbios_arguments(serial: str, bootloader_version: str) -> list:
    """Build the OpenMobile SMBIOS override arguments.

    - type 0 ``version`` -> DMI ``bios_version`` -> ``ro.bootloader``
    - type 1 ``manufacturer``/``product`` -> ``ro.product.*`` overrides
    - type 1 ``serial`` -> DMI ``product_serial`` -> ``ro.serialno``
    - type 3 ``manufacturer`` -> chassis vendor
    """
    return [
        "-smbios",
        f"type=0,vendor=OpenMobile,version={bootloader_version}",
        "-smbios",
        f"type=1,manufacturer=OpenMobile,product=OpenMobile-One,serial={serial}",
        "-smbios",
        "type=3,manufacturer=OpenMobile",
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
    parser.add_argument("--name", default="OpenMobile One")
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
        config["System"]["MemorySize"] = profile["memory_mib"]
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

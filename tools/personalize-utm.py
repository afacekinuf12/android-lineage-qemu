#!/usr/bin/env python3

import argparse
import plistlib
import secrets
import uuid
from pathlib import Path


HARDWARE_PROFILES = {
    "pixel-9-pro-compat": {
        "cpu_count": 8,
        "memory_mib": 16384,
        "dynamic_resolution": False,
        "additional_arguments": [
            "-smbios",
            "type=1,manufacturer=OpenMobile,product=OpenMobile-One",
            "-smbios",
            "type=3,manufacturer=OpenMobile",
        ],
    }
}


def locally_administered_mac() -> str:
    octets = bytearray(secrets.token_bytes(6))
    octets[0] = (octets[0] | 0x02) & 0xFE
    return ":".join(f"{octet:02X}" for octet in octets)


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
        arguments[:] = [
            argument.replace("product=OpenMobile One", "product=OpenMobile-One")
            for argument in arguments
        ]
        managed_arguments = profile["additional_arguments"]
        if not any(
            arguments[index : index + len(managed_arguments)] == managed_arguments
            for index in range(len(arguments) - len(managed_arguments) + 1)
        ):
            arguments.extend(managed_arguments)

    with config_path.open("wb") as destination:
        plistlib.dump(config, destination, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

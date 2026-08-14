#!/usr/bin/env python3

import argparse
import plistlib
import secrets
import uuid
from pathlib import Path


def locally_administered_mac() -> str:
    octets = bytearray(secrets.token_bytes(6))
    octets[0] = (octets[0] | 0x02) & 0xFE
    return ":".join(f"{octet:02X}" for octet in octets)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assign unique local identity to an extracted UTM VM."
    )
    parser.add_argument("vm", type=Path, help="path to the .utm bundle")
    parser.add_argument("--name", default="OpenMobile Virtual Device")
    args = parser.parse_args()

    config_path = args.vm / "config.plist"
    with config_path.open("rb") as source:
        config = plistlib.load(source)

    config["Information"]["UUID"] = str(uuid.uuid4()).upper()
    config["Information"]["Name"] = args.name
    for network in config.get("Network", []):
        network["MacAddress"] = locally_administered_mac()

    with config_path.open("wb") as destination:
        plistlib.dump(config, destination, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

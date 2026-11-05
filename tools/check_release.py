"""Check public runtime availability and the contents of release artifacts."""

from __future__ import annotations

import argparse
import urllib.request
import zipfile
from pathlib import Path

from source_robotics_leap_motion import __version__
from source_robotics_leap_motion.delivery import _descriptor, load_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="skip public runtime availability check"
    )
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    catalog = load_catalog()
    entry = catalog["runtimes"].get("windows-x86_64")
    if entry is None:
        raise SystemExit(
            "Release not configured: run tools/configure_release.py with the repository URL"
        )
    _descriptor(entry)
    if not args.offline:
        request = urllib.request.Request(entry["url"], method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            if int(response.headers.get("Content-Length", -1)) != entry["bytes"]:
                raise SystemExit("Public runtime download size differs from the pinned catalog")
    wheels = list(args.dist.glob(f"source_robotics_leap_motion-{__version__}-*.whl"))
    if not wheels:
        raise SystemExit("No built wheel to publish")
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if Path(name).suffix.lower() in (".exe", ".dll", ".pyd", ".ldat", ".jsonl"):
                    raise SystemExit(f"Unexpected native/private data in Python wheel: {name}")
            if "source_robotics_leap_motion/runtime_catalog.json" not in archive.namelist():
                raise SystemExit("Wheel is missing its runtime catalog")
    print("Release checks passed")


if __name__ == "__main__":
    main()

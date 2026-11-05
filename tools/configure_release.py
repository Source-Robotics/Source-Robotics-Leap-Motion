"""Pin local runtime release metadata to a concrete GitHub release URL."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from pathlib import Path

from source_robotics_leap_motion.delivery import CATALOG_SCHEMA, _descriptor


def configure(repository: str, tag: str, descriptor: Path, output: Path) -> dict:
    parsed = urllib.parse.urlsplit(repository.rstrip("/"))
    path = parsed.path.removesuffix(".git")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use a repository URL such as https://github.com/owner/repository")
    if not re.fullmatch(r"v[0-9A-Za-z._-]+", tag):
        raise ValueError("Use a version tag such as v0.1.0b1")
    entry = json.loads(descriptor.read_text(encoding="utf-8"))
    entry["url"] = (
        f"https://github.com{path}/releases/download/{tag}/"
        "source-leap-runtime-windows-x86_64-3.2.1.zip"
    )
    _descriptor(entry)
    catalog = {"schema": CATALOG_SCHEMA, "version": 1, "runtimes": {"windows-x86_64": entry}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("--tag", default="v0.1.0b1")
    parser.add_argument(
        "--descriptor", type=Path, default=Path("dist/runtime/runtime-descriptor.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("src/source_robotics_leap_motion/runtime_catalog.json")
    )
    args = parser.parse_args()
    print(json.dumps(configure(args.repository, args.tag, args.descriptor, args.output), indent=2))


if __name__ == "__main__":
    main()

"""Build a minimal Windows runtime release archive and its pinned download catalog."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from source_robotics_leap_motion.delivery import CATALOG_SCHEMA
from source_robotics_leap_motion.runtime_bundle import (
    DRIVER_FILES,
    MANIFEST,
    file_hash,
    inspect_runtime,
)


def build(
    runtime: Path,
    output: Path,
    *,
    drivers: Path | None = None,
    notice: Path | None = None,
    base_url: str | None = None,
) -> dict:
    report = inspect_runtime(runtime)
    if not report["redistribution_cleared"]:
        raise ValueError("The selected runtime manifest does not record redistribution clearance")
    manifest = json.loads((runtime / MANIFEST).read_text(encoding="utf-8"))
    origins = {entry["name"]: runtime / entry["name"] for entry in manifest["files"]}
    if drivers is not None:
        for name in DRIVER_FILES:
            origins[name] = drivers / Path(name).name
    if notice is not None:
        origins["NOTICE.txt"] = notice
    for origin in origins.values():
        if not origin.is_file():
            raise ValueError(f"Missing release file: {origin}")
    manifest["files"] = [
        {"name": name, "bytes": origin.stat().st_size, "sha256": file_hash(origin)}
        for name, origin in sorted(origins.items())
    ]
    output.mkdir(parents=True, exist_ok=True)
    filename = "source-leap-runtime-windows-x86_64-3.2.1.zip"
    archive = output / filename
    temporary = archive.with_suffix(".tmp")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as bundle:
        for name, origin in sorted(origins.items()):
            bundle.write(origin, arcname=name)
        bundle.writestr(MANIFEST, json.dumps(manifest, indent=2))
    temporary.replace(archive)
    descriptor = {
        "id": "legacy-windows-3.2.1",
        "url": (base_url.rstrip("/") + "/" + filename) if base_url else None,
        "bytes": archive.stat().st_size,
        "sha256": file_hash(archive),
        "unpacked_bytes": sum(entry["bytes"] for entry in manifest["files"]),
    }
    catalog = {
        "schema": CATALOG_SCHEMA,
        "version": 1,
        "runtimes": {"windows-x86_64": descriptor} if base_url else {},
    }
    (output / "runtime_catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (output / "runtime-descriptor.json").write_text(
        json.dumps(descriptor, indent=2), encoding="utf-8"
    )
    (output / "SHA256SUMS").write_text(
        descriptor["sha256"] + "  " + filename + "\n", encoding="utf-8"
    )
    return {"archive": str(archive), **descriptor, "public_url_configured": base_url is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--drivers", type=Path)
    parser.add_argument("--notice", type=Path)
    parser.add_argument(
        "--base-url", help="GitHub Release download URL, ending before the asset filename"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.runtime,
                args.output,
                drivers=args.drivers,
                notice=args.notice,
                base_url=args.base_url,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

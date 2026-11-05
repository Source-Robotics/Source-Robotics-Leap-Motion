"""Fetch the exact published GitHub wheel and sdist for the PyPI upload job."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

from source_robotics_leap_motion import __version__


def main():
    tag = os.environ.get("RELEASE_TAG", "v" + __version__)
    if tag != "v" + __version__:
        raise SystemExit("Release tag must match the tested source package version")
    repository = "Source-Robotics/Source-Robotics-Leap-Motion"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/tags/{tag}",
        headers={"User-Agent": "source-robotics-leap-release"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    if release["draft"]:
        raise SystemExit("A draft release cannot be published to PyPI")
    names = {
        f"source_robotics_leap_motion-{__version__}-py3-none-any.whl",
        f"source_robotics_leap_motion-{__version__}.tar.gz",
    }
    assets = {asset["name"]: asset for asset in release["assets"]}
    destination = Path("dist")
    destination.mkdir(exist_ok=True)
    for name in sorted(names):
        asset = assets[name]
        expected_url = f"https://github.com/{repository}/releases/download/{tag}/{name}"
        if asset["browser_download_url"] != expected_url:
            raise SystemExit("Unexpected release asset URL")
        digest = asset.get("digest", "")
        if not digest or not digest.startswith("sha256:"):
            raise SystemExit("GitHub asset has no SHA-256 digest")
        with urllib.request.urlopen(expected_url, timeout=30) as response:
            data = response.read(10 * 1024 * 1024 + 1)
        if len(data) != asset["size"] or hashlib.sha256(data).hexdigest() != digest[7:]:
            raise SystemExit("Release artifact size or SHA-256 mismatch")
        (destination / name).write_bytes(data)
        print(f"Verified {name}")


if __name__ == "__main__":
    main()

# Releasing

Package and runtime releases have separate versions. Python package versions b3 and
b4 reuse the pinned Windows 3.2.1 runtime hosted with **v0.1.0b1**.
A package or documentation change does not require regenerating the native archive.
Published wheel/sdist/runtime files are immutable: use a new version for changed bytes.

## Prepare a Python package release

1. Work on a branch. Set the new package version consistently in `pyproject.toml` and
   `src/source_robotics_leap_motion/__init__.py`. Update current user documentation
   and record the scope of validation.
2. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md) and review platform CI.
   Hardware claims require the corresponding real-device evidence; hosted CI alone
   is insufficient.
3. Build into a fresh output directory, inspect the artifacts, and check metadata:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install twine
   .\.venv\Scripts\python.exe -m build
   .\.venv\Scripts\python.exe -m twine check dist/*
   .\.venv\Scripts\python.exe tools/check_release.py
   ```

   `check_release.py` checks the public runtime size and the wheel's contents.
   `--offline` skips the network check. Setup verifies the full pinned runtime hash;
   the release HEAD request is not a replacement for that verification.
4. Install the exact candidate wheel in a fresh venv. Check dependencies, imports,
   the controller-free demo, and packaged viewer assets. Check live tracking when
   the release changes hardware/runtime behavior.
5. Merge the reviewed change and tag the corresponding source. Create the GitHub
   release with that version's exact tested wheel/sdist and SHA-256 checksums.
   Record the commit and artifact identities. Preserve any existing runtime pin
   unless this release deliberately changes the runtime.

The wheel must contain the package, viewer assets, `py.typed`, and runtime catalog.
It must exclude native vendor executables/DLLs/models, local recordings, credentials,
and `.tools/`/`.venv/`. The sdist includes maintained source, tests, examples, docs,
contributor instructions, and release utilities.

## Publish those artifacts to PyPI

The project uses GitHub Trusted Publishing with these registered fields:

```text
Project: source-robotics-leap-motion
Owner: Source-Robotics
Repository: Source-Robotics-Leap-Motion
Workflow: publish.yml
Environment: pypi
```

Run the manually dispatched [publish workflow](../.github/workflows/publish.yml) with
the exact existing release tag. It runs tests, downloads the GitHub wheel/sdist,
verifies GitHub's SHA-256 digests, checks metadata and runtime availability, and
uploads those same bytes through OIDC. No long-lived PyPI token is required.

After publication, verify the version-specific PyPI JSON/file digests against
GitHub and the tested local files. Test installation by package name in a fresh
venv and an upgrade from the preceding release. Check the actual installed version:
public indexes/caches can briefly show the preceding release immediately after upload.

See [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
for publisher administration. A normal documentation cleanup does not dispatch this
workflow or replace the current release.

## Prepare a new native runtime only when needed

Use approved runtime inputs and include original driver files and notices. The
existing runtime archive includes the allowlisted engine, model, firmware, VC++
support libraries, USB INF/CAT files, and notices, excluding the vendor GUI,
recordings, personal configuration, certificates, and private keys.

The [runtime tools](../tools/README.md) provide `build_runtime_release.py` and
`configure_release.py`; use their `--help` for inputs and choose a new immutable
runtime release tag. Configuration pins exact archive sizes and SHA-256. Changing
the archive requires updating the catalog and rebuilding the Python package.

Verify anonymous availability before distributing a package that references the
new runtime. Exercise download/cache/restart/client-sharing behavior and the
[clean-Windows hardware checklist](CLEAN_MACHINE_CHECK.md) before broadening installation
claims. Keep vendor notices in [VENDOR_NOTICE.txt](VENDOR_NOTICE.txt) with the payload.

[Documentation index](README.md)

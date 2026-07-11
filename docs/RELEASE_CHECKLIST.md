# Release checklist

1. Confirm the package version in `pyproject.toml` and update release notes.
2. Regenerate `constraints/windows.txt` using Windows and Python 3.10; review the complete diff.
3. Ensure Windows CI passes on Python 3.10–3.13, including unit and architecture tests.
4. On a clean Windows checkout, run `run_clipai.bat` and verify startup.
5. Create an annotated `v{version}` tag. Do not reuse or move a published tag.
6. Push the tag. The release workflow rejects mismatched tags, builds wheel/source archives, smoke-installs the wheel, and uploads artifacts.
7. Download the artifact and perform one final clean-machine startup check before publishing a GitHub Release.

This workflow does not publish to PyPI and does not build an executable installer.

# Release checklist

1. Confirm the package version in `pyproject.toml` and update release notes.
2. Regenerate `constraints/windows.txt` using Windows and Python 3.10; review the complete diff. The tag workflow separately uses pip-compile on Windows/Python 3.12 to create the hashed managed lock and wheelhouse; do not hand-edit either lock.
3. Ensure Windows CI passes on Python 3.10–3.13, including unit and architecture tests.
4. Run `python scripts/validate_language_packs.py`; verify every official pack, review record, fixed-output-language contract, Entry Panel candidate topology, and clean-checkout checksum.
5. On a clean Windows checkout, run `run_clipai.bat` and verify startup. If Action Language resources changed, exercise Tray selection, restart-only activation, Recent/flagship/More/search Action copy, selected-pack atomic recovery, and default-pack fail-closed behavior.
6. Confirm repository Actions configuration contains secret `CLIPAI_MANAGED_UPDATE_PRIVATE_KEY`, variable `CLIPAI_MANAGED_UPDATE_KEY_ID`, and variable `CLIPAI_MANAGED_UPDATE_TRUSTED_KEYRING`. The keyring is public JSON, must classify the selected key as `production`, and must retain every key still trusted for rotation. Never print or artifact the private key.
7. Create an annotated `v{version}` tag. Do not reuse or move a published tag.
8. Push the tag. The release workflow rejects non-official repositories and mismatched tags; builds wheel/source archives plus the hashed offline wheelhouse; signs and self-verifies the managed ZIP; generates `catalog.json`; and runs the complete managed-update gate.
9. Confirm the workflow creates a draft containing wheel, sdist, `clipai-managed-{version}.zip`, `catalog.json`, and `managed-update-trusted-keys.json`, then publishes it only after every gate succeeds. A failed run may leave a draft for inspection but must not leave a newly published Release.
10. On a clean managed installation, fetch `releases/latest/download/catalog.json`, perform one update, and confirm the prior version and shared user data remain intact.

This workflow does not publish to PyPI and does not build an executable installer.

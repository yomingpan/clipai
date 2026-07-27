# Windows source installation

ClipAI's source launcher uses 64-bit CPython 3.12 on Windows. Other installed
Python versions are left untouched.

## Recommended setup

1. Download or clone the repository.
2. Run `run_clipai.bat`.
3. Keep the first-run window open while ClipAI installs Python 3.12, creates
   `.venv`, and installs the constrained runtime packages.

The launcher prefers an existing Python 3.12 runtime. If none is available, it
uses WinGet to install the official Python Install Manager and then installs
Python 3.12. The Python bootstrap creates `.venv`; runtime packages are installed
with `constraints/windows.txt`, and development packages are not installed on
user machines. A fingerprint marker causes dependency installation to run again
only when `pyproject.toml` or the Windows constraints change.

If the active AI provider has no API key, ClipAI still starts and opens its
Provider Settings window. Entering and validating the key there writes the
required `.env` settings; the user does not need to create or edit `.env`
manually.

## Troubleshooting

- `Python 3.12 and WinGet are unavailable`: install the official
  [Python Install Manager](https://www.python.org/downloads/) and run the launcher again.
- An incompatible `.venv` is renamed to `.venv.incompatible` (or a numbered
  variant) before the Python 3.12 environment is created. It is not deleted.
- Missing constraints or pip failure: keep the complete source checkout and retain the displayed error. Do not disable TLS verification.
- To prepare without starting the app:
  `powershell -File scripts/bootstrap_windows.ps1 -NoLaunch`.

CI verifies constrained installation on every supported Python minor version. Constraints are regenerated intentionally on Windows using Python 3.10:

```powershell
python scripts/update_windows_constraints.py
```

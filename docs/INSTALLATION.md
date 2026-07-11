# Windows source installation

ClipAI supports 64-bit Windows with CPython 3.10, 3.11, 3.12, or 3.13.

## Recommended setup

1. Install a supported Python release and enable **Add Python to PATH**.
2. Download or clone the repository.
3. Run `run_clipai.bat` and confirm creation of `.venv`.

The launcher delegates environment creation to `scripts/bootstrap.py`. Runtime packages are installed with `constraints/windows.txt`; development packages are not installed on user machines.

## Troubleshooting

- `Python was not found`: install Python and reopen the terminal.
- `requires Python 3.10 through 3.13`: select a supported interpreter and remove an incompatible `.venv` manually.
- Missing constraints or pip failure: keep the complete source checkout and retain the displayed error. Do not disable TLS verification.
- To prepare without starting the app: `python scripts/bootstrap.py --no-launch`.

CI verifies constrained installation on every supported Python minor version. Constraints are regenerated intentionally on Windows using Python 3.10:

```powershell
python scripts/update_windows_constraints.py
```

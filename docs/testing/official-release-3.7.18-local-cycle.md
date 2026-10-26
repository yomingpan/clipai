# 3.7.18 exact official local cycle

Use the final downloaded official-mode Setup after provenance, payload extraction,
source and unsigned signature checks. This is developer-host evidence, not a clean
VM, reboot, browser trust or first-user observation. Record the actual Setup hash.

The existing acceptance helper now permits explicit `--product ClipAI`, with the
formal `ClipAI.Desktop` registration. Before any mutation it requires absent install
and shared roots and absent registration; it never repurposes user data. Candidate
is separate and must be preserved. Any existing formal installation blocks this
automatic cycle and needs a separately reviewed maintenance procedure.

```powershell
.venv/Scripts/python.exe -m experiments.first_install.accept_preview `
  --product ClipAI --version 3.7.18 `
  --setup <exact-final-ClipAI-Setup-3.7.18-windows-x64.exe> `
  --output <new-evidence-directory>
```

The cycle installs with empty PATH, checks owned identity/imports/Tk/registration/
shortcuts, rejects duplicate install and removal with a live owned process,
removes with a deliberately broken test venv, reinstalls with retained synthetic
data, then removes and cleans only its sentinel. It does not configure providers,
request AI or capture user content. Desktop startup is skipped if the user's app
is already running; a skip remains a skip in the evidence.

The release workflow runs the same cycle on its fresh Windows runner, choosing
Candidate on validation branches and formal ClipAI on tags. Receipts are included
in the uploaded output. Runner evidence does not assert standard-user status,
NIC isolation, reboot, a second logon session or human observation.

The formal installer roots are `%LOCALAPPDATA%/Programs/ClipAI` and
`%LOCALAPPDATA%/ClipAI`. The retained removal leaves its transaction evidence in
the new shared root. Do not automatically delete that root or general AppData.

Run this only against the exact intended product installer. The candidate
workflow builds `ClipAI Candidate`; using that binary with `--product ClipAI`
would not exercise the formal product and is prohibited by this runbook.

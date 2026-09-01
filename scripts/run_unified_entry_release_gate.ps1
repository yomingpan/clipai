$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "ClipAI virtual environment was not found at $python"
}

Push-Location $workspace
try {
    & $python -m pytest `
        tests\platform\test_entry_panel_hotkey.py `
        tests\app\test_runtime_entry_panel.py `
        tests\services\test_prepared_entry_input.py `
        tests\ui\test_primary_surface.py `
        tests\ui\test_unified_entry_panel.py `
        tests\architecture\test_unified_entry_panel_boundaries.py
    if ($LASTEXITCODE -ne 0) {
        throw "Unified Entry targeted gate failed."
    }

    & $python scripts\run_unit_tests.py
    if ($LASTEXITCODE -ne 0) {
        throw "ClipAI unit gate failed."
    }

    & $python -m compileall ClipAI
    if ($LASTEXITCODE -ne 0) {
        throw "ClipAI compile gate failed."
    }

    Write-Host "Automated Unified Entry gates passed."
    Write-Host "Complete docs\testing\unified-entry-panel-windows-release-checklist.md on an interactive Windows desktop before release."
}
finally {
    Pop-Location
}

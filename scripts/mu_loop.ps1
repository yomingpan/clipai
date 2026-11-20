param(
    [Parameter(Mandatory=$true)][string]$Step,
    [switch]$Desktop,
    [switch]$ExpectedRed
)
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
Set-Location (Join-Path $PSScriptRoot '..')
$out = 'artifacts/mu-loop.jsonl'
$tmp = Join-Path (Get-Location).Path ('.clipai-test-artifacts/mu-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force $tmp | Out-Null
$evidence = Join-Path $tmp 'evidence'
New-Item -ItemType Directory -Force $evidence | Out-Null
$rec = [ordered]@{
    schema=1; gate='mu-loop'; step=$Step; ts=(Get-Date).ToString('o')
    source_commit=(& git rev-parse HEAD); content_recorded=$false
    expected_red=[bool]$ExpectedRed; desktop_requested=[bool]$Desktop
}
function Suite([string]$name, [string[]]$targets) {
    $log = Join-Path $tmp ($name + '.txt')
    $base = Join-Path $tmp ($name + '-tmp')
    # Windows PowerShell wraps native stderr as ErrorRecord. Preserve diagnostics
    # and use the process exit code, including when faulthandler writes a stack.
    $ErrorActionPreference = 'Continue'
    $o = & $py -m pytest -q -p no:cacheprovider -o faulthandler_timeout=60 --basetemp $base @targets 2>&1 | Tee-Object -FilePath $log | Out-String
    $rec["${name}_exit"] = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    [IO.File]::WriteAllText($log, $o, (New-Object Text.UTF8Encoding $false))
    $rec["${name}_passed"] = if ($o -match '(\d+) passed') { [int]$Matches[1] } else { 0 }
    $rec["${name}_failed"] = if ($o -match '(\d+) failed') { [int]$Matches[1] } else { 0 }
    Write-Host "$name exit=$($rec["${name}_exit"]) passed=$($rec["${name}_passed"]) failed=$($rec["${name}_failed"]) log=$log"
}
$targeted = @(
    'tests/core/test_inline_dictation_view_contract.py', 'tests/core/test_inline_ports_contract.py',
    'tests/core/test_right_alt_contract.py',
    'tests/platform/test_right_alt_hotkey.py', 'tests/platform/test_selection_uia.py',
    'tests/platform/test_native_window.py', 'tests/platform/test_speech_output.py',
    'tests/platform/test_keyboard_state.py',
    'tests/platform/test_json_guidance_preferences.py', 'tests/services/test_inline_dictation_view.py',
    'tests/services/test_entry_panel.py', 'tests/app/test_runtime_interruption.py',
    'tests/app/test_runtime_voice_input.py', 'tests/ui/test_keyboard_confirm_gate.py',
    'tests/ui/test_inline_pill.py', 'tests/ui/test_voice_visuals.py', 'tests/ui/test_inline_dictation_owner.py',
    'tests/ui/test_result_dialog.py', 'tests/ui/test_unified_entry_panel.py',
    'tests/ui/test_input_recovery.py', 'tests/ui/test_shortcut_guide_ui.py',
    'tests/services/test_shortcut_guide.py', 'tests/ui/test_tray.py',
    'tests/ui/test_text_layout.py', 'tests/journeys/test_inline_dictation_journeys.py',
    'tests/ui/test_inline_dictation_window.py', 'tests/scripts/test_inline_trace_report.py',
    'tests/scripts/test_inline_observability_contract.py', 'tests/scripts/test_inline_measurement_recorder.py',
    'tests/scripts/test_inline_baseline_comparison.py', 'tests/scripts/test_inline_controlled_desktop_runner.py'
    'tests/scripts/test_uia_standby_probe.py', 'tests/scripts/test_inline_presentation_budget.py',
    'tests/scripts/test_inline_pill_focus_probe.py', 'tests/scripts/test_inline_pixel_presence_probe.py'
) | Where-Object { Test-Path $_ }
Suite 'targeted' $targeted
Suite 'architecture' @('tests/architecture')
Suite 'unit' @('tests', '-m', 'not integration')
$selectionOut = Join-Path $evidence 'selection.jsonl'
& $py scripts/selection_reliability_gate.py --iterations 3 --output $selectionOut | Out-Null
$rec.selection_gate_exit = $LASTEXITCODE
$rec.desktop_passed = $false
if ($Desktop) {
    if (Test-Path scripts/probe_inline_pill_focus.py) {
        $focusOut = Join-Path $evidence 'focus.jsonl'
        & $py scripts/probe_inline_pill_focus.py --output $focusOut | Out-Null
        $rec.focus_exit = $LASTEXITCODE
        $f = @(Get-Content $focusOut -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json })
        $rec.focus_cases = $f.Count
        $rec.focus_pass = @($f | Where-Object {
            $_.status -eq 'pass' -and $_.foreground_kept_on_show -and
            $_.foreground_kept_on_click -and $_.focused_control_kept -and $_.intent_received
        }).Count
    } else {
        $rec.focus_exit = 3
        $rec.focus_cases = 0
        $rec.focus_pass = 0
        $rec.focus_blocked = 'focus_probe_not_implemented'
    }
    $desktopOut = Join-Path $evidence 'desktop.jsonl'
    & $py scripts/selection_desktop_loop.py --mode auto --rounds 20 --output $desktopOut | Out-Null
    $rec.desktop_exit = $LASTEXITCODE
    # PowerShell 5.1 rejects an empty reason-histogram key. Parse aggregates only.
    $aggregate = & $py -c "import json,sys; rows=[json.loads(s) for s in open(sys.argv[1],encoding='utf-8') if s.strip()]; print(json.dumps({k:v for k,v in rows[-1].items() if k!='reason_histogram'}))" $desktopOut
    $s = $aggregate | ConvertFrom-Json
    $rec.desktop_cases = $s.cases
    $rec.desktop_passed_cases = $s.passed_cases
    $rec.desktop_p50_ms = $s.latency_ms.p50
    $rec.desktop_p95_ms = $s.latency_ms.p95
    $workers = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'selection_uia_worker' })
    $rec.uia_workers_after_stop = $workers.Count
    $rec.desktop_passed = ($rec.focus_exit -eq 0 -and $rec.focus_cases -ge 6 -and $rec.focus_pass -eq $rec.focus_cases -and
        $rec.desktop_exit -eq 0 -and $rec.desktop_cases -ge 100 -and $rec.desktop_passed_cases -eq $rec.desktop_cases -and
        $rec.desktop_p50_ms -le 300 -and $rec.desktop_p95_ms -le 1000 -and $rec.uia_workers_after_stop -eq 0)
}
# Only gate output is evidence. Pytest's temporary trees contain deliberate
# content fixtures and long-path failure cases; they must not be exported.
$rec.content_leak = [bool](Get-ChildItem $evidence -File -Filter *.jsonl | Select-String -Pattern '"(text|transcript|clipboard_text|selection_text)"\s*:\s*"[^"\s]')
$prev = if (Test-Path $out) {
    Get-Content $out -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.passed } | Select-Object -Last 1
} else { $null }
$rec.counts_preserved = (-not $prev) -or ($rec.unit_passed -ge $prev.unit_passed -and $rec.architecture_passed -ge $prev.architecture_passed)
# Baseline records the current checkout's counts; reference implementation counts
# are not evidence about this checkout and must not be fabricated.
$rec.passed = ($rec.targeted_exit -eq 0 -and $rec.architecture_exit -eq 0 -and $rec.unit_exit -eq 0 -and
    $rec.selection_gate_exit -eq 0 -and -not $rec.content_leak -and $rec.counts_preserved -and
    -not $ExpectedRed -and (-not $Desktop -or $rec.desktop_passed))
New-Item -ItemType Directory -Force artifacts | Out-Null
$j = $rec | ConvertTo-Json -Compress
[IO.File]::AppendAllText((Join-Path (Get-Location).Path $out), $j + "`n", (New-Object Text.UTF8Encoding $false))
Write-Host $j
if (-not $rec.passed) { exit 1 }

param([Parameter(Mandatory=$true)][string]$Step, [switch]$Desktop)
$ErrorActionPreference = 'Stop'
$py = '.venv\Scripts\python.exe'
$out = 'artifacts/branch-loop.jsonl'
$tmp = Join-Path (Get-Location).Path ('.clipai-test-artifacts/s-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force $tmp | Out-Null
$rec = [ordered]@{schema=1; gate='branch-loop'; step=$Step; ts=(Get-Date).ToString('o'); content_recorded=$false; expected_red=($Step -eq 'S3a')}
function Invoke-Suite([string]$name, [string[]]$targets) {
    $log = Join-Path $tmp ($name + '.txt')
    $base = Join-Path $tmp ($name + '-tmp')
    $o = & $py -m pytest -q -p no:cacheprovider -o faulthandler_timeout=30 --basetemp $base @targets 2>&1 | Tee-Object -FilePath $log | Out-String
    $rec["${name}_exit"] = $LASTEXITCODE
    [IO.File]::WriteAllText($log, $o, (New-Object Text.UTF8Encoding $false))
    $rec["${name}_passed"] = if ($o -match '(\d+) passed') { [int]$Matches[1] } else { 0 }
    $rec["${name}_failed"] = if ($o -match '(\d+) failed') { [int]$Matches[1] } else { 0 }
    Write-Host "$name exit=$($rec["${name}_exit"]) passed=$($rec["${name}_passed"]) failed=$($rec["${name}_failed"]) log=$log"
}
$targets = @('tests/core/test_selection_outcome.py','tests/platform/test_selection.py','tests/platform/test_selection_uia.py',
 'tests/services/test_prepared_entry_input.py','tests/services/test_selection_feedback.py','tests/app/test_runtime_entry_panel.py',
 'tests/ui/test_presentation_render.py','tests/ui/test_base_dialog.py','tests/scripts')
if ($Step -in @('baseline','S1','S2','S3a')) { $targets = @($targets | Where-Object { Test-Path $_ }) }
Invoke-Suite 'targeted' $targets
Invoke-Suite 'architecture' @('tests/architecture')
Invoke-Suite 'unit' @('tests','-m','not integration')
$gateOut = Join-Path $tmp 'gate.jsonl'
$gateArgs = @('--output', $gateOut)
if (Select-String -Path scripts/selection_reliability_gate.py -SimpleMatch -Pattern '"--iterations"' -Quiet) { $gateArgs += @('--iterations','3') }
& $py scripts/selection_reliability_gate.py @gateArgs | Out-Null
$rec.gate_exit = $LASTEXITCODE
# Windows PowerShell 5.1 cannot deserialize the legal empty reason key.
# Keep raw evidence unchanged; parse only the aggregate fields used here.
$aggregate = & $py -c "import json,sys; rows=[json.loads(s) for s in open(sys.argv[1],encoding='utf-8')]; print('\n'.join(json.dumps({k:v for k,v in r.items() if k!='reason_histogram'}) for r in rows))" $gateOut
$g = @($aggregate | ForEach-Object { $_ | ConvertFrom-Json })
$rec.gate_passed = -not ($g | Where-Object { -not $_.passed -or $_.nondeterministic })
$rec.gate_min_policy_rate = ($g | Measure-Object policy_correct_rate -Minimum).Minimum
$rec.gate_violations = ($g | ForEach-Object { $_.violations.PSObject.Properties.Value } | Measure-Object -Sum).Sum
$rec.gate_max_p95_ms = ($g | ForEach-Object { $_.latency_ms.p95 } | Measure-Object -Maximum).Maximum
$rec.gate_scenarios = $g[0].scenario_count
if ($Desktop) {
    $dOut = Join-Path $tmp 'desktop.jsonl'
    & $py scripts/selection_desktop_loop.py --mode auto --rounds 20 --output $dOut | Out-Null
    $rec.desktop_exit = $LASTEXITCODE
    $desktopAggregate = & $py -c "import json,sys; rows=[json.loads(s) for s in open(sys.argv[1],encoding='utf-8')]; print(json.dumps({k:v for k,v in rows[-1].items() if k!='reason_histogram'}))" $dOut
    $s = $desktopAggregate | ConvertFrom-Json
    $rec.desktop_cases = $s.cases; $rec.desktop_passed_cases = $s.passed_cases; $rec.desktop_p95_ms = $s.latency_ms.p95
}
$leak = Get-ChildItem $tmp -Filter *.jsonl | Select-String -SimpleMatch -Pattern 'verified selection','frozen clipboard','ClipAI selection loop sample'
$rec.content_leak = [bool]$leak
$previous = if (Test-Path $out) { Get-Content $out -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.passed } | Select-Object -Last 1 } else { $null }
$rec.test_counts_preserved = (-not $previous) -or (($rec.targeted_passed -ge $previous.targeted_passed) -and ($rec.architecture_passed -ge $previous.architecture_passed) -and ($rec.unit_passed -ge $previous.unit_passed))
$legacy = $Step -in @('baseline','S1','S2')
$ok = ($rec.targeted_exit -eq 0) -and ($rec.architecture_exit -eq 0) -and ($rec.unit_exit -eq 0) -and $rec.gate_passed `
 -and ($rec.gate_violations -eq 0) -and ($legacy -or (($rec.gate_max_p95_ms -lt 1) -and ($rec.gate_scenarios -eq 27))) `
 -and -not $rec.content_leak -and $rec.test_counts_preserved -and (-not $Desktop -or ($rec.desktop_exit -eq 0))
$rec.passed = $ok
New-Item -ItemType Directory -Force artifacts | Out-Null
$json = $rec | ConvertTo-Json -Compress
[IO.File]::AppendAllText((Join-Path (Get-Location).Path $out), $json + "`n", (New-Object Text.UTF8Encoding $false))
Write-Host $json
if (-not $ok) { exit 1 }

<#
Generate fixed, synthetic speech for attended Inline Dictation audio replay.
The phrases are public test data. Generated WAV files stay outside diagnostics.
#>
param(
    [string]$OutputDir = 'artifacts/inline-audio-fixtures'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$fixtureDir = [System.IO.Path]::GetFullPath($OutputDir)
[System.IO.Directory]::CreateDirectory($fixtureDir) | Out-Null

$fixtures = @(
    @{ language = 'zh-TW'; text = '你好，這是語音輸入測試。今天的天氣很好。'; file = 'zh-TW-fixed.wav' },
    @{ language = 'en-US'; text = 'Hello, this is a voice input test. The weather is nice today.'; file = 'en-US-fixed.wav' }
)

$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $records = @()
    foreach ($fixture in $fixtures) {
        $voice = $speaker.GetInstalledVoices() |
            Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq $fixture.language } |
            Select-Object -First 1
        if ($null -eq $voice) {
            throw "No installed speech voice for $($fixture.language)"
        }
        $speaker.SelectVoice($voice.VoiceInfo.Name)
        $wavPath = Join-Path $fixtureDir $fixture.file
        $speaker.SetOutputToWaveFile($wavPath)
        try {
            $speaker.Speak($fixture.text)
        }
        finally {
            $speaker.SetOutputToNull()
        }
        $records += [ordered]@{
            language = $fixture.language
            file = $fixture.file
            phrase = $fixture.text
            sha256 = (Get-FileHash -LiteralPath $wavPath -Algorithm SHA256).Hash.ToLowerInvariant()
            bytes = (Get-Item -LiteralPath $wavPath).Length
            voice = $voice.VoiceInfo.Name
        }
    }
    $manifest = [ordered]@{
        schema_version = 1
        source = 'Windows System.Speech fixed synthetic fixture'
        replay_method = 'speaker_to_built_in_microphone_acoustic_path'
        microphone_input_confirmed = $false
        fixtures = $records
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $fixtureDir 'manifest.json') -Encoding utf8
    Write-Output (Join-Path $fixtureDir 'manifest.json')
}
finally {
    $speaker.Dispose()
}

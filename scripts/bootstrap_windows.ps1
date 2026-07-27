[CmdletBinding()]
param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$RequiredPython = "3.12"
$PythonManagerPackage = "9NQ7512CXL7T"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Write-Stage {
    param([string]$Message)
    Write-Host "[clipai] $Message"
}

function Test-Python312 {
    param(
        [string]$Command,
        [string[]]$PrefixArguments = @()
    )

    try {
        $version = & $Command @PrefixArguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        return $LASTEXITCODE -eq 0 -and @($version)[-1].Trim() -eq $RequiredPython
    }
    catch {
        return $false
    }
}

function Get-PythonPath {
    param(
        [string]$Command,
        [string[]]$PrefixArguments = @()
    )

    if (-not (Test-Python312 -Command $Command -PrefixArguments $PrefixArguments)) {
        return $null
    }
    $path = & $Command @PrefixArguments -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return @($path)[-1].Trim()
}

function Get-PythonManager {
    $command = Get-Command "pymanager.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $windowsApps = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
    $candidates = @(
        (Join-Path $windowsApps "pymanager.exe")
    )
    $packageAliases = Get-ChildItem `
        -Path (Join-Path $windowsApps "PythonSoftwareFoundation.PythonManager_*") `
        -Filter "pymanager.exe" `
        -ErrorAction SilentlyContinue
    $candidates += $packageAliases.FullName

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Find-Python312 {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if ((Test-Path -LiteralPath $venvPython -PathType Leaf) -and
        (Test-Python312 -Command $venvPython)) {
        return $venvPython
    }

    $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        $path = Get-PythonPath -Command $py.Source -PrefixArguments @("-3.12")
        if ($path) {
            return $path
        }
    }

    $manager = Get-PythonManager
    if ($manager) {
        $path = Get-PythonPath -Command $manager -PrefixArguments @("-V:3.12")
        if ($path) {
            return $path
        }
    }

    $python312 = Get-Command "python3.12.exe" -ErrorAction SilentlyContinue
    if ($null -ne $python312 -and (Test-Python312 -Command $python312.Source)) {
        return $python312.Source
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $python -and (Test-Python312 -Command $python.Source)) {
        return $python.Source
    }
    return $null
}

function Install-Python312 {
    $manager = Get-PythonManager
    if (-not $manager) {
        $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
        if ($null -eq $winget) {
            throw "Python 3.12 and WinGet are unavailable. Install the Python Install Manager from https://www.python.org/downloads/ and run this launcher again."
        }

        Write-Stage "Installing the official Python Install Manager..."
        & $winget.Source install `
            --id $PythonManagerPackage `
            --exact `
            --source msstore `
            --accept-package-agreements `
            --accept-source-agreements `
            --disable-interactivity
        if ($LASTEXITCODE -ne 0) {
            throw "Python Install Manager installation failed with exit code $LASTEXITCODE."
        }
        $manager = Get-PythonManager
    }

    if (-not $manager) {
        throw "Python Install Manager was installed but is not available yet. Reopen this launcher."
    }

    Write-Stage "Installing Python 3.12..."
    & $manager install $RequiredPython
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.12 installation failed with exit code $LASTEXITCODE."
    }

    $python = Find-Python312
    if (-not $python) {
        throw "Python 3.12 was installed but could not be resolved."
    }
    return $python
}

try {
    Write-Stage "Checking for Python 3.12..."
    $python = Find-Python312
    if (-not $python) {
        $python = Install-Python312
    }

    Write-Stage "Using $python"
    $arguments = @((Join-Path $ProjectRoot "scripts\bootstrap.py"), "--yes")
    if ($NoLaunch) {
        $arguments += "--no-launch"
    }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "ClipAI environment setup failed with exit code $LASTEXITCODE."
    }
}
catch {
    Write-Error $_
    exit 1
}

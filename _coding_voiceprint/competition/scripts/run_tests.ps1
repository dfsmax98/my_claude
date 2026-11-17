$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "set_env.ps1")
Push-Location $env:VOICEPRINT_PROJECT_ROOT
try {
    python -m unittest discover -s tests\unit -p "test_*.py"
} finally {
    Pop-Location
}

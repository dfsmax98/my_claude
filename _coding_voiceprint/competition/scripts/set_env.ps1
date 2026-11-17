$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:VOICEPRINT_PROJECT_ROOT = $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:MODELSCOPE_CACHE = Join-Path $ProjectRoot "models\runtime\modelscope"
$env:PYTHONIOENCODING = "utf-8"

$PreferredPythonDir = "D:\asrvenv\Scripts"
if (Test-Path (Join-Path $PreferredPythonDir "python.exe")) {
    $env:Path = "$PreferredPythonDir;$env:Path"
}

Write-Host "VOICEPRINT_PROJECT_ROOT=$env:VOICEPRINT_PROJECT_ROOT"
Write-Host "MODELSCOPE_CACHE=$env:MODELSCOPE_CACHE"
Write-Host "PYTHON=$((Get-Command python).Source)"

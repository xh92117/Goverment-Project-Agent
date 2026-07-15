param(
  [string]$ConfigPath = "$PSScriptRoot\..\configs\knowledge-index-build.example.json"
)

$ErrorActionPreference = "Stop"

# Keep Chinese paths, JSON content, and stdout stable on Windows PowerShell.
chcp 65001 > $null
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  $Python = $VenvPython
} else {
  $Python = "python"
}

& $Python (Join-Path $PSScriptRoot "build_knowledge_index.py") --config $ConfigPath

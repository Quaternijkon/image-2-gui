param(
    [switch]$OneFile,
    [string]$Name = "gpt-image-batch"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Windows package with PyInstaller."
Write-Host "This script does not run automatically and does not embed API keys."

$mode = if ($OneFile) { "--onefile" } else { "--onedir" }

python -m pip install --upgrade pyinstaller
python -m PyInstaller `
    $mode `
    --name $Name `
    --collect-all PySide6 `
    --collect-data app `
    --add-data "app/api_capabilities.json;app" `
    --clean `
    --noconfirm `
    app/__main__.py

Write-Host "Build output is under dist/$Name."

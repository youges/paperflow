$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$paperflowPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $paperflowPython)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $paperflowPython -m pip install --disable-pip-version-check -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $paperflowPython -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; build stopped.' }
& $paperflowPython tools\build_release.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Ready: dist\PaperFlow.exe and dist\PaperFlow-Windows.zip'

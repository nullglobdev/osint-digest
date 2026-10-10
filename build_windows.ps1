param([string]$CompilerPath = "$PSScriptRoot\.build-tools\inno\ISCC.exe")
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $buildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        py -3 -m venv .build-venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
    }
    & $buildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed' }
    & $buildPython -m unittest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $buildPython packaging/make_icon.py
    & $buildPython -m PyInstaller --noconfirm --clean --log-level WARN OSINTDigest.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
    if (-not (Test-Path -LiteralPath $CompilerPath)) {
        throw 'Install Inno Setup 6, then rerun with -CompilerPath pointing to ISCC.exe. See DESKTOP.md.'
    }
    & $CompilerPath /Q packaging/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    Compress-Archive -Path dist/OSINTDigest -DestinationPath dist/OSINTDigest-Portable-1.0.0-x64.zip -Force
    Get-FileHash -Algorithm SHA256 -Path dist/installer/OSINTDigest-Setup-1.0.0-x64.exe,dist/OSINTDigest-Portable-1.0.0-x64.zip |
        ForEach-Object { '{0}  {1}' -f $_.Hash, [System.IO.Path]::GetFileName($_.Path) } |
        Set-Content -Encoding ASCII dist/SHA256SUMS.txt
    Write-Output 'Built installer and portable ZIP in dist.'
} finally {
    Pop-Location
}
exit 0

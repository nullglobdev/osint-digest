param([string]$CompilerPath = "$PSScriptRoot\..\.build-tools\inno\ISCC.exe")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $buildPython = Join-Path $projectRoot '.build-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        py -3 -m venv .build-venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
    }
    & $buildPython -m pip install -r requirements/build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed' }
    & $buildPython -m unittest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $buildPython packaging/windows/make_icon.py
    $appVersion = & $buildPython -c "from osint_digest.desktop.settings import VERSION; print(VERSION)"
    $distributionRoot = "dist/$appVersion"
    & $buildPython -m PyInstaller --noconfirm --clean --log-level WARN --distpath $distributionRoot packaging/windows/OSINTDigest.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
    if (-not (Test-Path -LiteralPath $CompilerPath)) {
        throw 'Install Inno Setup 6, then rerun with -CompilerPath pointing to ISCC.exe. See docs/DESKTOP.md.'
    }
    & $CompilerPath /Q "/DAppVersion=$appVersion" packaging/windows/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    $portablePath = "dist/OSINTDigest-Portable-$appVersion-x64.zip"
    $installerPath = "dist/installer/OSINTDigest-Setup-$appVersion-x64.exe"
    Compress-Archive -Path "$distributionRoot/OSINTDigest" -DestinationPath $portablePath -Force
    Get-FileHash -Algorithm SHA256 -Path $installerPath,$portablePath |
        ForEach-Object { '{0}  {1}' -f $_.Hash, [System.IO.Path]::GetFileName($_.Path) } |
        Set-Content -Encoding ASCII dist/SHA256SUMS.txt
    Write-Output 'Built installer and portable ZIP in dist.'
} finally {
    Pop-Location
}
exit 0

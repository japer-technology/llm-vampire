$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $RepoRoot

$VersionArgs = @()
if ($env:RELEASE_TAG) {
    $VersionArgs = @("--tag", $env:RELEASE_TAG)
}
$Version = (& python scripts/packaging/version.py @VersionArgs).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Version validation failed"
}
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($Architecture -ne "x64") {
    throw "Unsupported Windows architecture: $Architecture"
}
$Architecture = "x86_64"
$env:RELEASE_VERSION = $Version

$BuildDir = Join-Path $RepoRoot "build/pyinstaller-windows"
$DistDir = Join-Path $RepoRoot "dist"
$PortableName = "LMStudio-Vampire-$Version-windows-$Architecture-portable.zip"
$InstallerName = "LMStudio-Vampire-$Version-windows-$Architecture.exe"
Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $BuildDir, $DistDir | Out-Null

uv run --frozen --extra packaging pyinstaller `
    --clean --noconfirm `
    --distpath (Join-Path $BuildDir "dist") `
    --workpath (Join-Path $BuildDir "work") `
    packaging/windows/LMStudioVampire.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed"
}

$AppDir = Join-Path $BuildDir "dist/LMStudioVampire"
$Executable = Join-Path $AppDir "LMStudioVampire.exe"
if (-not (Test-Path $Executable -PathType Leaf)) {
    throw "Expected executable is missing: $Executable"
}
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath (Join-Path $DistDir $PortableName) -Force

$Iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6/ISCC.exe"
if (-not (Test-Path $Iscc -PathType Leaf)) {
    throw "Inno Setup 6 is required: $Iscc"
}
& $Iscc `
    "/DAppVersion=$Version" `
    "/DSourceDir=$AppDir" `
    "/DOutputDir=$DistDir" `
    "/DOutputBaseFilename=$([IO.Path]::GetFileNameWithoutExtension($InstallerName))" `
    packaging/windows/installer.iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed"
}

foreach ($Artifact in @($PortableName, $InstallerName)) {
    $Path = Join-Path $DistDir $Artifact
    if (-not (Test-Path $Path -PathType Leaf) -or (Get-Item $Path).Length -eq 0) {
        throw "Expected artifact is missing or empty: $Path"
    }
    Write-Host "Built $Path"
}

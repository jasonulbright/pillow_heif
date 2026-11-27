# Builds the decode-only pillow_heif wheel for Windows x64.
#
#   pwsh -File spectra\build-windows.ps1 -Python C:\Path\To\python.exe
#
# libheif and libde265 are built from their pinned release archives with MSVC
# and the static CRT, with every encoder and every other codec off. The binding
# is built from the committed tree. Needs Visual Studio with the x64 C++ tools
# (cmake and ninja are the copies Visual Studio installs).
param(
    [Parameter(Mandatory)][string]$Python,
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) "pillow-heif-spectra"),
    [string]$OutDir = (Join-Path $PSScriptRoot "..\spectra-dist")
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

function Invoke-Checked([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "REFUSED: $What failed (exit $LASTEXITCODE)" }
}

$Pins = @{}
foreach ($line in Get-Content (Join-Path $PSScriptRoot "pins.env")) {
    if ($line -and -not $line.StartsWith("#")) { $k, $v = $line -split "=", 2; $Pins[$k] = $v }
}

$Downloads = Join-Path $WorkDir "downloads"
$Src = Join-Path $WorkDir "src"
$Build = Join-Path $WorkDir "build"
$Prefix = Join-Path $WorkDir "prefix"
$Unrepaired = Join-Path $WorkDir "unrepaired"
$Dist = Join-Path $WorkDir "dist"
$BuildVenv = Join-Path $WorkDir "venv-build"
$TestVenv = Join-Path $WorkDir "venv-test"
foreach ($d in @($Src, $Build, $Prefix, $Unrepaired, $Dist, $BuildVenv, $TestVenv)) {
    if (Test-Path $d) { Remove-Item $d -Recurse -Force }
}
New-Item -ItemType Directory -Force $Downloads, $Src, $Build, $Prefix, $Dist | Out-Null

$Tar = Join-Path $env:SystemRoot "System32\tar.exe"
foreach ($lib in @("LIBHEIF", "LIBDE265")) {
    $archive = Join-Path $Downloads (Split-Path $Pins["${lib}_URL"] -Leaf)
    if (-not (Test-Path $archive)) {
        Invoke-WebRequest -Uri $Pins["${lib}_URL"] -OutFile $archive -MaximumRetryCount 4 -RetryIntervalSec 10
    }
    $actual = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
    if ($actual -ne $Pins["${lib}_SHA256"]) { throw "REFUSED: $archive has sha256 $actual" }
    Invoke-Checked "extracting $lib" { & $Tar -xzf $archive -C $Src }
}
$HeifSrc = Join-Path $Src "libheif-$($Pins.LIBHEIF_VERSION)"
$De265Src = Join-Path $Src "libde265-$($Pins.LIBDE265_VERSION)"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "REFUSED: no Visual Studio installation with the x64 C++ tools" }
$CMake = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$Ninja = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
foreach ($line in (cmd /c "`"$vcvars`" >nul 2>&1 && set")) {
    if ($line -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] }
}
# /Brepro drops the link timestamp and other per-run fields.
$env:CL = "/Brepro"
$env:LINK = "/Brepro"
$env:SOURCE_DATE_EPOCH = $Pins.SOURCE_DATE_EPOCH

$Common = @("-GNinja", "-DCMAKE_MAKE_PROGRAM=$Ninja", "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_INSTALL_PREFIX=$Prefix", "-DBUILD_SHARED_LIBS=ON",
    # Static CRT: no Microsoft runtime is ever vendored. Every allocation that
    # crosses a DLL boundary is released by the DLL that made it.
    "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded")
$De265Options = @(Get-Content (Join-Path $PSScriptRoot "libde265-options.txt") | Where-Object { $_ })
$HeifOptions = @(Get-Content (Join-Path $PSScriptRoot "libheif-options.txt") | Where-Object { $_ })

$De265Build = Join-Path $Build "libde265"
Invoke-Checked "libde265 configure" { & $CMake -S $De265Src -B $De265Build @Common @De265Options }
Invoke-Checked "libde265 build" { & $CMake --build $De265Build }
Invoke-Checked "libde265 install" { & $CMake --install $De265Build }

$HeifBuild = Join-Path $Build "libheif"
Invoke-Checked "libheif configure" { & $CMake -S $HeifSrc -B $HeifBuild @Common "-DCMAKE_PREFIX_PATH=$Prefix" @HeifOptions }
$cache = Get-Content (Join-Path $HeifBuild "CMakeCache.txt")
if (-not ($cache | Select-String -Pattern "^LIBDE265_LIBRARY:" | Where-Object { $_ -notmatch "NOTFOUND" })) {
    throw "REFUSED: libheif configure did not find libde265"
}
if ($cache | Select-String -Pattern "^X265_LIBRARY:[^=]*=(?!.*NOTFOUND).") { throw "REFUSED: libheif configure found x265" }
Invoke-Checked "libheif build" { & $CMake --build $HeifBuild }
Invoke-Checked "libheif install" { & $CMake --install $HeifBuild }
# setup.py links `libheif` and reads headers from <prefix>\include\libheif.
Copy-Item (Join-Path $Prefix "lib\heif.lib") (Join-Path $Prefix "lib\libheif.lib") -Force

Invoke-Checked "build venv" { & $Python -m venv $BuildVenv }
$VPy = Join-Path $BuildVenv "Scripts\python.exe"
Invoke-Checked "build tooling" {
    & $VPy -m pip install --disable-pip-version-check --require-hashes --no-deps -r (Join-Path $PSScriptRoot "build-requirements-windows.txt")
}
$Binding = Join-Path $Src "binding"
Invoke-Checked "staging the binding" { & $VPy (Join-Path $PSScriptRoot "stage.py") $Binding $HeifSrc $De265Src windows }
$env:MSYS2_PREFIX = $Prefix
Invoke-Checked "binding build" {
    & $VPy -m pip wheel --disable-pip-version-check --no-build-isolation --no-deps --no-index -w $Unrepaired $Binding
}
$built = @(Get-ChildItem $Unrepaired -Filter "pillow_heif-$($Pins.WHEEL_VERSION)-*-win_amd64.whl")
if ($built.Count -ne 1) { throw "REFUSED: expected one wheel in $Unrepaired" }
Invoke-Checked "delvewheel repair" {
    & (Join-Path $BuildVenv "Scripts\delvewheel.exe") repair -w $Dist --add-path (Join-Path $Prefix "bin") $built[0].FullName
}
$wheel = Get-Item (Join-Path $Dist $built[0].Name)
Invoke-Checked "import inventory" { & $VPy (Join-Path $PSScriptRoot "check_imports.py") $wheel.FullName }

Invoke-Checked "test venv" { & $Python -m venv $TestVenv }
$TPy = Join-Path $TestVenv "Scripts\python.exe"
Invoke-Checked "pillow install" {
    & $TPy -m pip install --disable-pip-version-check --require-hashes --only-binary :all: --no-deps -r (Join-Path $PSScriptRoot "test-requirements-windows.txt")
}
Invoke-Checked "wheel install" { & $TPy -m pip install --disable-pip-version-check --no-index --no-deps $wheel.FullName }
Invoke-Checked "wheel verification" { & $TPy -I (Join-Path $PSScriptRoot "verify_wheel.py") $wheel.FullName }

New-Item -ItemType Directory -Force $OutDir | Out-Null
Copy-Item $wheel.FullName $OutDir -Force
$sha = (Get-FileHash -Algorithm SHA256 (Join-Path $OutDir $wheel.Name)).Hash.ToLowerInvariant()
Write-Host "Wrote $($wheel.Name) sha256 $sha"

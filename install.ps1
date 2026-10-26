# MIDI-GPT for Ableton Live: installer (Windows, PowerShell 5.1 or later).
#
#   1. the device: downloads the release zip and copies the MIDI-GPT folder into Live's User Library
#   2. the server (optional, asked): a Python environment with midigpt, Hugging Face access, the model, and
#      Start MIDI-GPT Server shortcuts (to MIDI-GPT\Server\Start MIDI-GPT Server.bat)
#
#   irm https://metacreation.net/midigpt-live/bootstrap.ps1 | iex
#   powershell -ExecutionPolicy Bypass -File install.ps1 [options]
#
# Options
#   -Zip PATH             install the device from a local release zip (default: latest GitHub release)
#   -Version X.Y.Z        install that release instead of the latest
#   -UserLibrary DIR      Live's User Library (default: read from Live's preferences)
#   -Server | -NoServer   set up the local server, or skip it (default: ask)
#   -ServerDir DIR        where the server's Python environment goes (default: %APPDATA%\MIDI-GPT\server)
#   -Model NAME           yellow_medium (default, 350 MB) or yellow_small (83 MB, faster)
#   -Gpu | -Cpu           the CUDA or the CPU build of PyTorch (default: CUDA when an NVIDIA GPU is found, asked)
#   -Yes                  accept every default without asking (a Hugging Face token is then read from HF_TOKEN)
#   -Uninstall            remove the device folder, the server environment, the shortcuts and the settings
#
# Environment: MIDIGPT_LIVE_REPO (owner/repo of the releases), MIDIGPT_VERSION (midigpt package version), HF_TOKEN.

param(
    [string]$Zip = "",
    [string]$Version = "",
    [string]$UserLibrary = "",
    [switch]$Server,
    [switch]$NoServer,
    [string]$ServerDir = "",
    [string]$Model = "",
    [switch]$Gpu,
    [switch]$Cpu,
    [switch]$Yes,
    [switch]$Uninstall,
    [switch]$Help
)

# Not "Stop": Windows PowerShell 5.1 turns any stderr line of a native command (pip, python) into a terminating
# error under "Stop". Native commands are checked with $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest's progress bar slows downloads to a crawl on 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

if ($Help) { Get-Content $MyInvocation.MyCommand.Path | Select-Object -Skip 1 -First 20 | ForEach-Object { $_ -replace '^# ?', '' }; exit 0 }

$Repo = if ($env:MIDIGPT_LIVE_REPO) { $env:MIDIGPT_LIVE_REPO } else { "Metacreation-Lab/midigpt-LIVE" }
$MidigptVersion = if ($env:MIDIGPT_VERSION) { $env:MIDIGPT_VERSION } else { "0.4.1" }
$Port = 3456
$PythonMaxMinor = 14   # midigpt has wheels for Python 3.10-3.14
$HfRepo = "Metacreation/MIDI-GPT"

# ------------------------------------------------------------------ helpers
function Write-Bold { param($m) Write-Host $m -ForegroundColor White }
function Write-Step { param($m) Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Write-OK   { param($m) Write-Host "    " -NoNewline; Write-Host "OK " -ForegroundColor Green -NoNewline; Write-Host $m }
function Write-Warn { param($m) Write-Host "    " -NoNewline; Write-Host "!  " -ForegroundColor Yellow -NoNewline; Write-Host $m }
function Stop-Install {
    param($m)
    Write-Host ""; Write-Host "Error: " -ForegroundColor Red -NoNewline; Write-Host $m
    if ($env:MIDIGPT_INTERACTIVE) { Read-Host "Press Enter to close" | Out-Null }
    exit 1
}
function Test-Command { param($c) $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }
function Test-Interactive { -not [Console]::IsInputRedirected }

# Ask "question" default(y|n) -> $true for yes. -Yes, or no console, takes the default.
function Confirm-Step {
    param([string]$Question, [string]$Default = "y")
    $hint = if ($Default -eq "n") { "[y/N]" } else { "[Y/n]" }
    if ($Yes -or -not (Test-Interactive)) { $ans = $Default }
    else { $ans = Read-Host "    $Question $hint"; if (-not $ans) { $ans = $Default } }
    return $ans -match '^[Yy]'
}

$ConfigDir = Join-Path $env:APPDATA "MIDI-GPT"
$Config = Join-Path $ConfigDir "live.json"
if (-not $ServerDir) { $ServerDir = Join-Path $ConfigDir "server" }
$Venv = Join-Path $ServerDir ".venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"

# live.json is the device's settings file (also written by the device's Node helper): keep the other keys
function Get-ConfigValue {
    param([string]$Key)
    try { return (Get-Content -Raw $Config -ErrorAction Stop | ConvertFrom-Json).$Key } catch { return "" }
}
function Set-ConfigValue {
    param([string]$Key, [string]$Value)
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    $cfg = $null
    try { $cfg = Get-Content -Raw $Config -ErrorAction Stop | ConvertFrom-Json } catch { }
    if (-not $cfg) { $cfg = New-Object PSObject }
    $cfg | Add-Member -NotePropertyName $Key -NotePropertyValue $Value -Force
    [System.IO.File]::WriteAllText($Config, ($cfg | ConvertTo-Json) + "`n")
}

# Live's User Library: <ProjectPath>\User Library from the newest Live's Library.cfg
function Find-UserLibrary {
    $cfg = Get-ChildItem -Path (Join-Path $env:APPDATA "Ableton") -Filter Library.cfg -Recurse -Depth 3 -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($cfg) {
        $m = Select-String -Path $cfg.FullName -Pattern '<ProjectPath Value="([^"]*)"' | Select-Object -First 1
        if ($m) {
            $p = Join-Path $m.Matches[0].Groups[1].Value "User Library"
            if (Test-Path $p) { return $p }
        }
    }
    return Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Ableton\User Library"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "MIDI-GPT"
$ShortcutName = "Start MIDI-GPT Server.lnk"

function New-Shortcut {
    param([string]$Path, [string]$Target)
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut($Path)
    $lnk.TargetPath = $Target
    $lnk.WorkingDirectory = Split-Path -Parent $Target
    $lnk.Description = "The MIDI-GPT server for the Ableton Live device"
    $lnk.Save()
}

if (-not $UserLibrary) { $UserLibrary = Find-UserLibrary }
$DeviceDir = Join-Path $UserLibrary "MIDI-GPT"

# ------------------------------------------------------------------ uninstall
if ($Uninstall) {
    Write-Bold "Uninstall MIDI-GPT for Live"
    $installed = Get-ConfigValue install_dir
    if (-not $installed) { $installed = $DeviceDir }
    if ((Test-Path $installed) -and (Confirm-Step "Remove the devices in $installed?" "y")) { Remove-Item -Recurse -Force $installed; Write-OK "removed $installed" }
    $sd = Get-ConfigValue server_dir
    if (-not $sd) { $sd = $ServerDir }
    if ((Test-Path $sd) -and (Confirm-Step "Remove the server environment in ${sd}?" "y")) { Remove-Item -Recurse -Force $sd; Write-OK "removed $sd" }
    foreach ($s in @((Join-Path $Desktop $ShortcutName), $StartMenu)) {
        if (Test-Path $s) { Remove-Item -Recurse -Force $s; Write-OK "removed $s" }
    }
    if ((Test-Path $Config) -and (Confirm-Step "Remove the saved settings ($Config)?" "y")) { Remove-Item -Force $Config; Write-OK "removed settings" }
    Write-Host ""
    Write-Host "    Downloaded models stay in $env:USERPROFILE\.cache\huggingface (delete models--Metacreation--MIDI-GPT there"
    Write-Host "    to free the space), and so does a saved Hugging Face token (hf auth logout removes it)."
    exit 0
}

Write-Bold "MIDI-GPT for Ableton Live"
Write-Host "    device  -> $DeviceDir"

# ------------------------------------------------------------------ 1. device
Write-Step "1/2  Installing the device"
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("midigpt-live-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
    if (-not $Zip) {
        $api = if ($Version) { "https://api.github.com/repos/$Repo/releases/tags/v$Version" } else { "https://api.github.com/repos/$Repo/releases/latest" }
        try { $rel = Invoke-RestMethod -Uri $api -UseBasicParsing } catch { Stop-Install "Could not reach GitHub ($api)." }
        $asset = $rel.assets | Where-Object { $_.name -like "MIDI-GPT-for-Live-*.zip" } | Select-Object -First 1
        if (-not $asset) { Stop-Install "No MIDI-GPT-for-Live zip found in the release at $api." }
        Write-Host "    downloading $($asset.name)"
        $Zip = Join-Path $Tmp "device.zip"
        try { Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $Zip -UseBasicParsing } catch { Stop-Install "Download failed: $($asset.browser_download_url)" }
    }
    if (-not (Test-Path $Zip)) { Stop-Install "Not found: $Zip" }
    $Unzipped = Join-Path $Tmp "unzipped"
    try { Expand-Archive -Path $Zip -DestinationPath $Unzipped -Force } catch { Stop-Install "Could not unzip $Zip" }
    if (-not (Test-Path (Join-Path $Unzipped "MIDI-GPT\MIDI-GPT.amxd"))) { Stop-Install "$Zip does not contain MIDI-GPT\MIDI-GPT.amxd" }

    if (-not (Test-Path $UserLibrary)) {
        Write-Warn "Live's User Library was not found at $UserLibrary"
        if (-not (Confirm-Step "Create it there anyway? (or re-run with -UserLibrary DIR)" "y")) { Stop-Install "Cancelled." }
    }
    New-Item -ItemType Directory -Force -Path $DeviceDir | Out-Null
    # replace the devices and the Server folder, keep anything else the user put in the folder
    Copy-Item -Path (Join-Path $Unzipped "MIDI-GPT\*") -Destination $DeviceDir -Recurse -Force
    # files from the internet are blocked until unblocked (the Windows counterpart of the macOS quarantine)
    Get-ChildItem -Path $DeviceDir -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
Set-ConfigValue install_dir $DeviceDir
Write-OK "MIDI-GPT.amxd and MIDI-GPT Instrument.amxd are in the User Library (Live browser: User Library > MIDI-GPT)"

# ------------------------------------------------------------------ 2. server
Write-Step "2/2  MIDI-GPT server"
$SetUp = if ($Server) { $true } elseif ($NoServer) { $false } else {
    Write-Host "    The device needs a MIDI-GPT server. Set one up on this computer now? Skip this if you"
    Write-Host "    use a server on another machine (enter its address in the device's SETUP page)."
    Confirm-Step "Set up a local server?" "y"
}
$Launch = Join-Path $DeviceDir "Server\Start MIDI-GPT Server.bat"

if (-not $SetUp) {
    Write-OK "skipped (re-run with -Server to set it up later)"
} else {
    if (-not (Test-Path $Launch)) { Stop-Install "This release has no Server folder with the server launchers: install 0.2.1 or later." }

    # --- Python 3.10-3.14 (midigpt has prebuilt wheels for those): uv, else the py launcher, else python
    function Test-PythonOk {
        param([string[]]$Cmd)
        $exe = $Cmd[0]; $rest = @($Cmd | Select-Object -Skip 1)
        & $exe @rest -c "import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, $PythonMaxMinor)))" 2>$null
        return $LASTEXITCODE -eq 0
    }
    $Uv = ""
    $Py = $null
    if (Test-Command uv) { $Uv = (Get-Command uv).Source }
    elseif (Test-Path "$env:USERPROFILE\.local\bin\uv.exe") { $Uv = "$env:USERPROFILE\.local\bin\uv.exe" }
    else {
        $candidates = @()
        if (Test-Command py) { foreach ($v in @("3.12", "3.13", "3.14", "3.11", "3.10")) { $candidates += , @("py", "-$v") } }
        $candidates += , @("python3"); $candidates += , @("python")
        foreach ($c in $candidates) { if ((Test-Command $c[0]) -and (Test-PythonOk $c)) { $Py = $c; break } }
        if (-not $Py) {
            Write-Host "    No Python 3.10-3.$PythonMaxMinor found. uv (https://docs.astral.sh/uv) can install one just for MIDI-GPT."
            if (-not (Confirm-Step "Install uv?" "y")) { Stop-Install "Install Python 3.12 (python.org, or: winget install Python.Python.3.12) and run this again." }
            powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
            $Uv = "$env:USERPROFILE\.local\bin\uv.exe"
            if (-not (Test-Path $Uv)) { Stop-Install "uv install failed." }
        }
    }

    New-Item -ItemType Directory -Force -Path $ServerDir | Out-Null
    if ((Test-Path $VenvPy) -and (Test-PythonOk @($VenvPy))) {
        Write-OK "using the existing environment in $Venv"
    } else {
        Remove-Item -Recurse -Force $Venv -ErrorAction SilentlyContinue
        if ($Uv) { & $Uv venv -q --python 3.12 $Venv } else { $exe = $Py[0]; $rest = @($Py | Select-Object -Skip 1); & $exe @rest -m venv $Venv }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) { Stop-Install "Could not create the environment in $Venv." }
        Write-OK "created $Venv ($(& $VenvPy -V 2>&1))"
    }

    # --- PyTorch needs the Microsoft Visual C++ runtime (14.40 or newer), which fresh Windows installs may lack:
    # pip installs torch fine, then "import torch" fails with WinError 126
    $arch = if ((& $VenvPy -c "import platform; print(platform.machine())" 2>$null) -eq "ARM64") { "arm64" } else { "x64" }
    $vc = $null
    foreach ($k in @("HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\$arch", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\$arch")) {
        $rt = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
        if ($rt -and $rt.Installed -eq 1) { $vc = [version]"$($rt.Major).$($rt.Minor).$($rt.Bld)"; break }
    }
    if (-not $vc -or $vc -lt [version]"14.40") {
        $url = "https://aka.ms/vc14/vc_redist.$arch.exe"
        Write-Host "    PyTorch needs the Microsoft Visual C++ Redistributable (14.40 or newer)."
        if (Confirm-Step "Download and install it from Microsoft? (Windows asks for administrator permission)" "y") {
            $exe = Join-Path ([System.IO.Path]::GetTempPath()) "vc_redist.$arch.exe"
            try {
                Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
                $sig = Get-AuthenticodeSignature -FilePath $exe
                if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") { throw "not signed by Microsoft" }
                $p = Start-Process -FilePath $exe -ArgumentList "/install", "/quiet", "/norestart" -Verb RunAs -Wait -PassThru -ErrorAction Stop
                if (@(0, 1638, 3010) -contains $p.ExitCode) { Write-OK "Visual C++ runtime installed" } else { throw "exit code $($p.ExitCode)" }
            } catch {
                Write-Warn "The Visual C++ runtime wasn't installed ($_). Install it from $url"
            } finally {
                Remove-Item $exe -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Warn "Install it later from $url, or the server won't start."
        }
    }

    # --- midigpt, and PyTorch: PyPI's Windows build is CPU-only; the CUDA build comes from PyTorch's own index
    $useGpu = $false
    if ($Gpu) { $useGpu = $true }
    elseif (-not $Cpu -and (Test-Command nvidia-smi)) {
        $useGpu = Confirm-Step "An NVIDIA GPU was found. Install the CUDA build of PyTorch (about 2.5 GB, faster)?" "y"
    }
    function Invoke-Pip {
        param([string[]]$PipArgs)
        if ($Uv) { & $Uv pip install -q --python $VenvPy @PipArgs } else { & $VenvPy -m pip install -q @PipArgs }
        return $LASTEXITCODE -eq 0
    }
    if (-not $Uv) { & $VenvPy -m pip install -q --upgrade pip 2>$null | Out-Null }
    Write-Host "    installing midigpt $MidigptVersion and torch (a few minutes the first time)"
    if ($useGpu) {
        if (-not (Invoke-Pip @("torch", "--index-url", "https://download.pytorch.org/whl/cu126"))) { Stop-Install "Installing the CUDA build of PyTorch failed (re-run with -Cpu for the CPU build)." }
    }
    if (-not (Invoke-Pip @("midigpt[http,inference]==$MidigptVersion"))) { Stop-Install "Installing midigpt failed." }
    & $VenvPy -c "import midigpt.http.server, midigpt.inference.engine" 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Install "midigpt installed but does not import (if the error mentions a DLL, install https://aka.ms/vc14/vc_redist.$arch.exe)." }
    Write-OK "midigpt $(& $VenvPy -c "import importlib.metadata as m; print(m.version('midigpt'))") installed"

    if (-not $Model) {
        $Model = "yellow_medium"
        if (-not $Yes -and (Test-Interactive)) {
            Write-Host "    Model: 1) yellow_medium  350 MB, best results (default)"
            Write-Host "           2) yellow_small    83 MB, faster on older computers"
            if ((Read-Host "    Choose [1/2]") -eq "2") { $Model = "yellow_small" }
        }
    }

    # --- the launchers are in the release's Server folder; they read the model and port from server.conf, and the
    # server folder from live.json
    [System.IO.File]::WriteAllText((Join-Path $ServerDir "server.conf"),
        "# written by install.ps1: the model and port the launchers use`r`nMODEL=$Model`r`nPORT=$Port`r`n")
    Set-ConfigValue server_dir $ServerDir
    New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
    New-Shortcut -Path (Join-Path $StartMenu $ShortcutName) -Target $Launch
    $Launchers = @($Launch)
    if (Confirm-Step "Put a 'Start MIDI-GPT Server' shortcut on the Desktop?" "y") {
        New-Shortcut -Path (Join-Path $Desktop $ShortcutName) -Target $Launch
        $Launchers += (Join-Path $Desktop $ShortcutName)
    }
    Write-OK "launcher: $Launch (and in the Start menu)"

    # --- Hugging Face access: the checkpoints are gated (an account that accepted the license, and a token)
    # Python snippets run from a temp file (5.1 mangles double quotes in native arguments), with HF_TOKEN left out:
    # what counts is the saved token, the one the launcher's server will use.
    function Invoke-HfPython {
        param([string]$Code, [string[]]$PyArgs = @(), [hashtable]$Env = @{})
        $tmp = [System.IO.Path]::GetTempFileName() + ".py"
        Set-Content -Path $tmp -Value $Code -Encoding ASCII
        $saved = $env:HF_TOKEN
        Remove-Item Env:HF_TOKEN -ErrorAction SilentlyContinue
        foreach ($k in $Env.Keys) { Set-Item "Env:$k" $Env[$k] }
        try {
            $out = & $VenvPy $tmp @PyArgs 2>$null
            return @{ Out = ("$($out | Select-Object -Last 1)").Trim(); Code = $LASTEXITCODE }
        } finally {
            foreach ($k in $Env.Keys) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
            if ($null -ne $saved) { $env:HF_TOKEN = $saved }
            Remove-Item $tmp -ErrorAction SilentlyContinue
        }
    }
    # cached (already downloaded), ok, nologin (no token saved), gated (the token's account has no access), offline
    function Get-HfAccess {
        $r = Invoke-HfPython -PyArgs @($HfRepo, $Model) -Code @'
import glob, os, sys
from huggingface_hub import constants, get_hf_file_metadata, get_token, hf_hub_url
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
repo, model = sys.argv[1:]
snapshots = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "snapshots")
if glob.glob(os.path.join(snapshots, "*", model + "-*.safetensors")):
    print("cached"); sys.exit()
try:
    from midigpt.inference.engine import _resolve_checkpoint_filename
    get_hf_file_metadata(hf_hub_url(repo, _resolve_checkpoint_filename(repo, model)))
    print("ok")
except (GatedRepoError, RepositoryNotFoundError):
    print("gated" if get_token() else "nologin")
'@
        if ($r.Code -ne 0 -or -not $r.Out) { return "offline" }
        return $r.Out
    }
    # saves a token where midigpt-http finds it (~\.cache\huggingface\token), passed in the environment
    function Save-HfToken {
        param([string]$Token)
        $r = Invoke-HfPython -Env @{ MIDIGPT_HF_TOKEN = $Token } -Code @'
import os
from huggingface_hub import login
login(token=os.environ["MIDIGPT_HF_TOKEN"], add_to_git_credential=False)
'@
        return $r.Code -eq 0
    }
    $Hf = Join-Path $Venv "Scripts\hf.exe"
    $access = Get-HfAccess
    switch ($access) {
        "cached"  { Write-OK "the $Model model is already downloaded" }
        "ok"      { Write-OK "Hugging Face: access to $HfRepo" }
        "offline" { Write-Warn "Couldn't reach Hugging Face; the server downloads the model on its first start." }
        default {
            if ($Yes -or -not (Test-Interactive)) {
                if ($env:HF_TOKEN -and (Save-HfToken $env:HF_TOKEN)) { $access = Get-HfAccess }
                if ($access -eq "ok") { Write-OK "Hugging Face: access to $HfRepo (HF_TOKEN saved)" }
                else {
                    Write-Warn "No access to ${HfRepo}: accept its license at https://huggingface.co/$HfRepo, then run"
                    Write-Warn "'$Hf auth login' (or install again with HF_TOKEN set)."
                }
            } else {
                Write-Host ""
                Write-Host "    The MIDI-GPT models are on Hugging Face and need a free account to download:"
                Write-Host "      1. Sign in at https://huggingface.co and accept the license at https://huggingface.co/$HfRepo"
                Write-Host "      2. Create an access token at https://huggingface.co/settings/tokens (type `"Read`" is enough)"
                if ($access -eq "gated") { Write-Host "    (A token is saved, but its account has no access yet: accept the license, or paste another token.)" }
                while ($true) {
                    $secure = Read-Host "    Paste the token (hidden), or press Enter to skip" -AsSecureString
                    $tok = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
                    if (-not $tok) {
                        if ($access -eq "gated") { $access = Get-HfAccess }
                        if ($access -eq "ok") { Write-OK "Hugging Face: access to $HfRepo" }
                        else { Write-Warn "Skipped. The server will say what is missing when it starts; run '$Hf auth login' later." }
                        break
                    }
                    if (-not (Save-HfToken $tok)) { Write-Warn "That token was refused; try again."; continue }
                    $access = Get-HfAccess
                    if ($access -eq "ok") { Write-OK "token saved; access to $HfRepo"; break }
                    if ($access -eq "gated") { Write-Warn "Token saved, but this account has no access yet: accept the license at https://huggingface.co/$HfRepo, then press Enter." }
                    else { Write-Warn "Token saved; Hugging Face couldn't be reached to check it."; break }
                }
            }
        }
    }

    if ((@("ok", "offline") -contains $access) -and (Confirm-Step "Download the $Model model now? (otherwise on the server's first start)" "y")) {
        $r = Invoke-HfPython -PyArgs @($HfRepo, $Model) -Code @'
import sys
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import GatedRepoError
from midigpt.inference.engine import _resolve_checkpoint_filename
repo, model = sys.argv[1:]
try:
    print(hf_hub_download(repo_id=repo, filename=_resolve_checkpoint_filename(repo, model)))
except GatedRepoError:
    print("gated"); sys.exit(1)
'@
        if ($r.Code -eq 0) { Write-OK $r.Out }
        elseif ($r.Out -eq "gated") { Write-Warn "No access to $HfRepo yet: accept its license at https://huggingface.co/$HfRepo, then start the server." }
        else { Write-Warn "Download failed; the server will try again when it starts." }
    }
}

# ------------------------------------------------------------------ done
Write-Step "Done"
$first = if ($SetUp) { $Launchers[-1] } else { "your MIDI-GPT server" }
Write-Host "    1. Start the server: $first"
Write-Host "    2. In Live: User Library > MIDI-GPT > drag MIDI-GPT onto a track, then open its window."
Write-Host "    3. The server address is in SETUP (default http://127.0.0.1:$Port)."
if ($SetUp -and -not $Yes -and (Test-Interactive) -and (Confirm-Step "Start the server now?" "n")) { Start-Process -FilePath $Launch -WorkingDirectory (Split-Path -Parent $Launch) }
if ($env:MIDIGPT_INTERACTIVE) { Read-Host "Press Enter to close" | Out-Null }

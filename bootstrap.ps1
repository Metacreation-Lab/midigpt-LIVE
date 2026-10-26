# One-line install of MIDI-GPT for Ableton Live (Windows, PowerShell):
#
#   irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1 | iex
#
# Downloads install.ps1 and runs it. Options go through a script block, e.g.
#   & ([scriptblock]::Create((irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1))) -NoServer
#
# Everything runs in a function that only returns: piped into iex this has no process of its own, so exit would
# close the caller's PowerShell window.

function Install-MidigptLive {
    $repo = if ($env:MIDIGPT_LIVE_REPO) { $env:MIDIGPT_LIVE_REPO } else { "Metacreation-Lab/midigpt-LIVE" }
    $branch = if ($env:MIDIGPT_LIVE_BRANCH) { $env:MIDIGPT_LIVE_BRANCH } else { "HEAD" }   # HEAD = the default branch
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $dir = Join-Path ([System.IO.Path]::GetTempPath()) ("midigpt-live-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $script = Join-Path $dir "install.ps1"
    try {
        try {
            Invoke-WebRequest -Uri "https://raw.githubusercontent.com/$repo/$branch/install.ps1" -OutFile $script -UseBasicParsing
        } catch {
            Write-Host "Could not download install.ps1 from $repo ($branch)." -ForegroundColor Red
            return
        }
        # a separate process: the execution policy doesn't apply to it, and its exit can't close this window
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script @args
    } finally {
        Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    }
}

Install-MidigptLive @args

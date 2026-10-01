# Offline behavioral checks. No SSH, task registration, mount, or production file access.
param([Parameter(Mandatory=$true)][string]$Scratch)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../scripts/backup-pull.ps1')
$Destination = $Scratch
function Get-BackupDestination { return $Destination }
function Get-BackupFreeBytes { return $script:FreeBytes }
function Assert-True { param($Value, [string]$Message); if (-not $Value) { throw $Message } }
function Expect-Stop {
    param([scriptblock]$Action, [string]$Expected)
    try { & $Action; throw 'Expected failure did not happen' }
    catch { if ($_.Exception.Message -notlike ('*' + $Expected + '*')) { throw } }
}
$name = 'vzdump-qemu-320-2026_09_30-05_05_00.vma.zst'
$old = 'vzdump-qemu-320-2026_09_29-05_05_00.vma.zst'
$script:Data = [byte[]](0..255)
$algorithm = [Security.Cryptography.SHA256]::Create()
$hash = [BitConverter]::ToString($algorithm.ComputeHash($script:Data)).Replace('-', '').ToLowerInvariant()
$algorithm.Dispose()
$script:Manifest = "$name`t256`t$hash`n$old`t256`t$hash`n"
$script:Gets = 0
$script:FreeBytes = 200GB
$script:Corrupt = $false
$script:Changed = $false
function Invoke-BackupSsh {
    param([string]$Command, [string]$OutputPath = '')
    if ($Command -eq 'list') {
        if ($script:Changed -and $script:Gets -gt 0) { return $script:Manifest.Replace($hash, ('0' * 64)) }
        return $script:Manifest
    }
    Assert-True ($Command -eq ('get ' + $name)) 'Only the newest archive may be fetched'
    $script:Gets++
    if ($script:Corrupt) { [IO.File]::WriteAllBytes($OutputPath, [byte[]](255..0)) }
    else { [IO.File]::WriteAllBytes($OutputPath, $script:Data) }
}
New-Item -ItemType Directory -Path $Destination | Out-Null
Invoke-BackupPull | Out-Null
$target = Join-Path $Destination $name
Assert-True ((Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant() -eq $hash) 'Copied hash differs'
Assert-True ($script:Gets -eq 1) 'Expected one newest archive'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $Destination $old))) 'Old archive was copied'
Assert-True ((Get-Content -LiteralPath (Join-Path $Destination 'pull.log') -Raw) -match 'NAS_UNCHANGED=true') 'Acceptance log missing'
$before = (Get-Item -LiteralPath $target).LastWriteTimeUtc
Invoke-BackupPull | Out-Null
Assert-True ($script:Gets -eq 1 -and (Get-Item -LiteralPath $target).LastWriteTimeUtc -eq $before) 'Existing archive was fetched or changed'
$script:FreeBytes = 99GB
Expect-Stop { Invoke-BackupPull | Out-Null } 'less than 100 GB'
Assert-True (Test-Path -LiteralPath $target) 'Low-space stop removed an archive'
$script:FreeBytes = 200GB
[IO.File]::WriteAllBytes($target, [byte[]](1,2,3))
Expect-Stop { Invoke-BackupPull | Out-Null } 'Existing archive hash differs'
Assert-True ((Get-Item -LiteralPath $target).Length -eq 3) 'Existing mismatched archive overwritten'
# Separate scratch destinations: failed downloads must not publish a final name.
$Destination = Join-Path $Scratch 'bad-hash'
New-Item -ItemType Directory -Path $Destination | Out-Null
$script:Corrupt = $true
Expect-Stop { Invoke-BackupPull | Out-Null } 'Downloaded SHA-256 differs'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $Destination $name))) 'Bad hash published'
Assert-True (@(Get-ChildItem -LiteralPath $Destination -Filter '*.partial').Count -eq 1) 'Partial was deleted'
$Destination = Join-Path $Scratch 'nas-changed'
New-Item -ItemType Directory -Path $Destination | Out-Null
$script:Corrupt = $false
$script:Changed = $true
$script:Gets = 0
Expect-Stop { Invoke-BackupPull | Out-Null } 'NAS archive changed'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $Destination $name))) 'Changed source published'
Expect-Stop { ConvertFrom-ArchiveList "../bad`t1`t$hash" } 'Invalid archive manifest'
Write-Output 'PASS: newest per VM, identical hashes, skip, free-space stop, no overwrite, corrupt transfer, changed NAS, strict manifest'

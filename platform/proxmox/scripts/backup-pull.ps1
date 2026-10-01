# Daily append-only pulls while workstation is awake. Never wakes the computer.
[CmdletBinding()]
param(
    [string]$Destination = 'D:\homelab-backups',
    [string]$NodeAddress = '192.168.0.11',
    [string]$Identity = (Join-Path $HOME '.ssh/homelab_backup_pull_ed25519'),
    [string]$KnownHosts = 'D:\homelab-backups\control\known_hosts',
    [string]$SshExecutable = 'C:\Windows\System32\OpenSSH\ssh.exe'
)
$ErrorActionPreference = 'Stop'
$ArchivePattern = '^vzdump-(?:qemu|lxc)-(?<vmid>[0-9]{3,5})-(?<date>[0-9]{4}_[0-9]{2}_[0-9]{2}-[0-9]{2}_[0-9]{2}_[0-9]{2})\.(?:vma|tar)\.(?:zst|gz|lzo)$'

function ConvertFrom-ArchiveList {
    param([string]$Text)
    foreach ($line in ($Text -split '\r?\n')) {
        if ($line -eq '') { continue }
        $parts = $line -split "`t"
        if ($parts.Count -ne 3 -or $parts[0] -cnotmatch $ArchivePattern -or
            $parts[1] -notmatch '^[0-9]+$' -or $parts[2] -cnotmatch '^[0-9a-f]{64}$') {
            throw 'Invalid archive manifest; nothing is trusted'
        }
        $name = $parts[0]
        if ($name -cnotmatch $ArchivePattern) { throw 'Invalid name' }
        [pscustomobject]@{Name=$name; VMID=$Matches.vmid; Date=$Matches.date; Size=[long]$parts[1]; SHA256=$parts[2]}
    }
}

function Get-NewestArchives {
    param([object[]]$Archives)
    @($Archives | Group-Object VMID | ForEach-Object {
        $_.Group | Sort-Object Date, Name -Descending | Select-Object -First 1
    })
}

function Get-BackupFreeBytes {
    param([string]$Directory)
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Directory)))
    $drive.AvailableFreeSpace
}

function Invoke-BackupSsh {
    param([string]$Command, [string]$OutputPath = '')
    if ($Command -ne 'list' -and $Command -cnotmatch ('^get ' + $ArchivePattern.TrimStart('^'))) {
        throw 'Unsupported remote command'
    }
    if ($NodeAddress -notmatch '^[0-9.]+$') { throw 'Invalid node address' }
    if (-not (Test-Path -LiteralPath $KnownHosts -PathType Leaf)) { throw 'Verified host pin is missing' }
    $arguments = @('-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', ('UserKnownHostsFile=' + $KnownHosts), '-o', 'GlobalKnownHostsFile=NUL',
        '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3', '-i', $Identity, ('root@' + $NodeAddress), $Command)
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $SshExecutable
    # Fixed, validated arguments; works with the built-in Windows PowerShell 5.1.
    $start.Arguments = ($arguments | ForEach-Object {
        if ($_ -match '["\r\n]') { throw 'Invalid SSH argument' }
        '"' + $_ + '"'
    }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $file = $null
    $started = $false
    try {
        if (-not $process.Start()) { throw 'SSH did not start' }
        $started = $true
        $errors = $process.StandardError.ReadToEndAsync()
        if ($OutputPath) {
            $file = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $process.StandardOutput.BaseStream.CopyTo($file)
            $file.Flush($true)
            $file.Dispose()
            $file = $null
        } else {
            $text = $process.StandardOutput.ReadToEnd()
        }
        $process.WaitForExit()
        $errorText = $errors.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw ('SSH failed: ' + $errorText.Trim()) }
        if (-not $OutputPath) { return $text }
    } finally {
        if ($file) { $file.Dispose() }
        if ($started -and -not $process.HasExited) { $process.Kill() }
        $process.Dispose()
    }
}

function Write-BackupLog {
    param([string]$Message)
    $line = [DateTime]::UtcNow.ToString('o') + ' ' + $Message
    Add-Content -LiteralPath (Join-Path $Destination 'pull.log') -Value $line -Encoding UTF8
    Write-Output $line
}

function Get-BackupDestination {
    $folder = [IO.Path]::GetFullPath($Destination)
    if (-not $folder.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination must be on D:' }
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { throw 'Destination is not installed' }
    return $folder
}

function Invoke-BackupPull {
    $minimum = 100GB
    $folder = Get-BackupDestination
    $lock = $null
    try {
        $lock = [IO.File]::Open((Join-Path $folder 'pull.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $free = Get-BackupFreeBytes $folder
        if ($free -lt $minimum) { throw 'D: has less than 100 GB free; copies stopped, nothing deleted' }
        $listingBefore = Invoke-BackupSsh 'list'
        $all = @(ConvertFrom-ArchiveList $listingBefore)
        if ($all.Count -eq 0) { throw 'No finalized archives found' }
        if (@($all | Group-Object Name | Where-Object Count -gt 1).Count) { throw 'Duplicate manifest name' }
        $pending = @()
        foreach ($archive in (Get-NewestArchives $all)) {
            $target = Join-Path $folder $archive.Name
            if (Test-Path -LiteralPath $target) {
                if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archive.SHA256) {
                    throw ('Existing archive hash differs: ' + $archive.Name + '; retained for review')
                }
                Write-BackupLog ('VERIFIED existing ' + $archive.Name + ' SHA256=' + $archive.SHA256)
                continue
            }
            if ((Get-BackupFreeBytes $folder) - $archive.Size -lt $minimum) {
                throw ('Insufficient space to copy ' + $archive.Name + ' and retain 100 GB free')
            }
            $partial = $target + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
            # Failed partial files are retained for review; this script never deletes.
            Invoke-BackupSsh ('get ' + $archive.Name) $partial
            if ((Get-Item -LiteralPath $partial).Length -ne $archive.Size) { throw 'Downloaded archive size differs' }
            $digest = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($digest -ne $archive.SHA256) { throw ('Downloaded SHA-256 differs: ' + $archive.Name) }
            $pending += [pscustomobject]@{Archive=$archive; Partial=$partial; Target=$target; Digest=$digest}
        }
        # Hashing the NAS manifest is costly: one before/after pair for the whole batch.
        if ($pending.Count) {
            $after = @(ConvertFrom-ArchiveList (Invoke-BackupSsh 'list'))
        }
        foreach ($copy in $pending) {
            $archive = $copy.Archive
            $remote = @($after | Where-Object Name -eq $archive.Name)
            if ($remote.Count -ne 1 -or $remote[0].Size -ne $archive.Size -or $remote[0].SHA256 -ne $archive.SHA256) {
                throw ('NAS archive changed during pull: ' + $archive.Name)
            }
            # File.Move does not overwrite; same-directory rename is atomic.
            [IO.File]::Move($copy.Partial, $copy.Target)
            Write-BackupLog ('COPIED ' + $archive.Name + ' bytes=' + $archive.Size + ' SHA256=' + $copy.Digest + ' NAS_UNCHANGED=true')
        }
        Write-BackupLog 'SUCCESS all newest-per-VMID archives verified'
    } catch {
        Write-BackupLog ('STOP ' + $_.Exception.Message)
        throw
    } finally {
        if ($lock) { $lock.Dispose() }
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-BackupPull }

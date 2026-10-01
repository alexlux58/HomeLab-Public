# Run only AFTER the operator's exact Proxmox stage approval was executed.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$NodeConfig,
    [Parameter(Mandatory=$true)][string]$HostPublicKeyFile,
    [string]$TaskName = 'HomeLab Backup Pull'
)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $NodeConfig -Raw | ConvertFrom-Json
$nodeAddresses = @{pve1='192.168.0.11'; pve2='192.168.0.12'; pve='192.168.0.13'}
# Public pins only; the contract test requires exact equality with inventory/lab.yml.
$nodeFingerprints = @{
    pve1='SHA256:EXAMPLE_FINGERPRINT_REDACTED'
    pve2='SHA256:EXAMPLE_FINGERPRINT_REDACTED'
    pve='SHA256:EXAMPLE_FINGERPRINT_REDACTED'
}
if ($config.node -notin @('pve1', 'pve2', 'pve') -or
    $config.address -ne $nodeAddresses[$config.node] -or
    $config.fingerprint -cne $nodeFingerprints[$config.node]) { throw 'Node config differs from approved inventory identity' }
$hostLines = @(Get-Content -LiteralPath $HostPublicKeyFile | Where-Object { $_ -notmatch '^#' -and $_.Trim() })
if ($hostLines.Count -ne 1 -or $hostLines[0] -cnotmatch ('^' + [regex]::Escape($config.address) + ' ssh-ed25519 [A-Za-z0-9+/]{68}$')) {
    throw 'Provide exactly the selected node public ED25519 host key line'
}
$sshKeygen = 'C:\Windows\System32\OpenSSH\ssh-keygen.exe'
$printed = & $sshKeygen -lf $HostPublicKeyFile -E sha256
if ($LASTEXITCODE -ne 0 -or $printed -notmatch ('\s' + [regex]::Escape($config.fingerprint) + '\s')) {
    throw 'Host fingerprint does not match inventory/lab.yml; stop, never auto-accept'
}
$control = 'D:\homelab-backups\control'
$scriptTarget = Join-Path $control 'backup-pull.ps1'
$pinTarget = Join-Path $control 'known_hosts'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Task already exists; review an update separately' }
if (Test-Path -LiteralPath $pinTarget) { throw 'Pin file already exists; review instead of replacing it' }
New-Item -ItemType Directory -Path $control -Force | Out-Null
# Copy public host pin only after the fingerprint comparison above.
[IO.File]::WriteAllText($pinTarget, $hostLines[0] + "`n", [Text.Encoding]::ASCII)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'backup-pull.ps1') -Destination $scriptTarget -ErrorAction Stop
$xml = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'backup-pull-task.xml') -Raw
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$xml = $xml.Replace('__OPERATOR_SID__', $sid).Replace('__NODE_ADDRESS__', $config.address)
Register-ScheduledTask -TaskName $TaskName -Xml $xml | Out-Null
Write-Output ('Installed ' + $TaskName + '; daily 06:30, missed-start catch-up, WakeToRun=false, logged-in operator only')

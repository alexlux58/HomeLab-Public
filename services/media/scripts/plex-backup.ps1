# Copy Plex's own database backups and Preferences.xml to the NAS.
# Append-only: robocopy without /MIR or /PURGE never deletes at the target.
# Preferences.xml holds the Plex token, so the destination share must be
# readable only by the operator (L6/L7 tables). This script never prints it.
param(
  [Parameter(Mandatory = $true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'Plex Media Server'
$databases = Join-Path $root 'Plug-in Support\Databases'
$stamp = Get-Date -Format 'yyyyMMdd'

# Plex writes dated database backups itself (Scheduled Tasks setting).
robocopy $databases (Join-Path $Destination 'databases') '*.db-20*' /XO /R:2 /W:10 /NP /NFL /NDL | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy databases failed with $LASTEXITCODE" }

$prefs = Join-Path $root 'Preferences.xml'
$prefsDest = Join-Path $Destination 'preferences'
New-Item -ItemType Directory -Force -Path $prefsDest | Out-Null
Copy-Item -LiteralPath $prefs -Destination (Join-Path $prefsDest "Preferences-$stamp.xml")
Write-Output "Plex metadata backup copied to $Destination"

<#
.SYNOPSIS
  Cleans transient files left by launcher bat scripts and stale pycache.

.DESCRIPTION
  Removes known junk files from the project root and stale __pycache__
  directories under APP/. Safe to run at any time — only deletes
  regenerable/transient artifacts.

.USAGE
  .\tools\cleanup.ps1              # clean root junk
  .\tools\cleanup.ps1 -Full        # also prune __pycache__ and .pyc
#>
[CmdletBinding()]
param(
    [switch]$Full
)

$ErrorActionPreference = 'SilentlyContinue'

$junkFiles = @(
    'console_err.txt',
    'console_out.txt',
    'err.txt',
    'out.txt',
    'last_bat_err.txt',
    'last_bat_out.txt',
    'update_log.txt'
)

$root = Split-Path -Parent $PSScriptRoot

foreach ($f in $junkFiles) {
    $p = Join-Path $root $f
    if (Test-Path $p) {
        Remove-Item -LiteralPath $p -Force
        Write-Host "Removed: $f"
    }
}

if ($Full) {
    Get-ChildItem -Path (Join-Path $root 'APP') -Recurse -Directory -Filter '__pycache__' |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force; Write-Host "Removed: $($_.FullName)" }
    Get-ChildItem -Path $root -Filter '*.pyc' -Recurse |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    Write-Host "Pruned __pycache__ and .pyc files."
}

Write-Host "Cleanup complete."

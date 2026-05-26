#Requires -Version 5.1
<#
.SYNOPSIS
  Network lab control (Windows / Docker Desktop)

.EXAMPLE
  .\scripts\lab.ps1 up
  .\scripts\lab.ps1 down
  .\scripts\lab.ps1 generate
  .\scripts\lab.ps1 status
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "restart", "generate", "status", "logs", "detect-gateway")]
    [string]$Command = "up",

    [string]$Config = ""  # auto: lab.yaml or lab.json
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Config) {
    if (Test-Path "config\lab.yaml") { $Config = "config\lab.yaml" }
    elseif (Test-Path "config\lab.json") { $Config = "config\lab.json" }
    else { $Config = "config\lab.yaml.example" }
}

function Ensure-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py -3" }
    throw "Python 3 is required. Install from https://www.python.org/downloads/"
}

function Invoke-Generate {
    $py = Ensure-Python
    & $py scripts/generate_compose.py -c $Config
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Command) {
    "generate" {
        Invoke-Generate
    }
    "up" {
        Invoke-Generate
        docker compose build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        docker compose up -d
    }
    "down" {
        docker compose down
    }
    "restart" {
        Invoke-Generate
        docker compose down
        docker compose build
        docker compose up -d
    }
    "status" {
        docker compose ps
    }
    "logs" {
        docker compose logs -f
    }
    "detect-gateway" {
        $py = Ensure-Python
        & $py scripts/host_network.py -j
    }
}

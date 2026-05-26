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
    else { $Config = "config\lab.json.example" }
}

function Test-Python3Candidate {
    param(
        [string]$Exe,
        [string[]]$Prefix = @()
    )
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) {
        return $false
    }
    $cmd = Get-Command $Exe
    # Microsoft Store の空スタブを除外
    if ($cmd.Source -match "WindowsApps\\python\d?\.exe$") {
        return $false
    }
    try {
        $versionLines = & $Exe @Prefix "--version" 2>&1
        $code = $LASTEXITCODE
        $text = ($versionLines | Out-String).Trim()
        if ($code -ne 0) { return $false }
        if ($text -notmatch "Python 3\.") { return $false }
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $candidates = @(
        @{ Exe = "py"; Prefix = @("-3") },
        @{ Exe = "python3"; Prefix = @() },
        @{ Exe = "python"; Prefix = @() }
    )

    foreach ($c in $candidates) {
        if (-not (Test-Python3Candidate -Exe $c.Exe -Prefix $c.Prefix)) {
            continue
        }
        Write-Host "Using Python: $($c.Exe) $($c.Prefix -join ' ')" -ForegroundColor DarkGray
        & $c.Exe @($c.Prefix + $Arguments)
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        return
    }

    Write-Host ""
    Write-Host "Python 3 が見つかりません。" -ForegroundColor Red
    Write-Host "  Windows で 'python' とだけ表示される場合、ストア用スタブだけが入っていることがあります。" -ForegroundColor Yellow
    Write-Host "  対処:" -ForegroundColor Yellow
    Write-Host "    1. https://www.python.org/downloads/ から Python 3 をインストール" -ForegroundColor Yellow
    Write-Host "    2. インストーラで 'Add python.exe to PATH' にチェック" -ForegroundColor Yellow
    Write-Host "    3. 設定 → アプリ → アプリ実行エイリアス で 'python.exe' をオフ" -ForegroundColor Yellow
    Write-Host "    4. 新しい PowerShell を開き: py -3 --version" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

function Invoke-Generate {
    Invoke-Python -Arguments @("scripts/generate_compose.py", "-c", $Config)
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
        Invoke-Python -Arguments @("scripts/host_network.py", "-j")
    }
}

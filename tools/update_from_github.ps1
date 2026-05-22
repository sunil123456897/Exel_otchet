param(
    [string]$RepoOwner = "sunil123456897",
    [string]$RepoName = "Exel_otchet",
    [string]$Branch = "main",
    [switch]$Launch
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogFile = Join-Path $Root "update_log.txt"
$StateDir = Join-Path $Root ".update_state"
$BackupRoot = Join-Path $Root ".update_backups"
$LocalSettings = @("APP\config.yaml", "APP\employees.yaml")

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Backup-LocalSettings {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDir = Join-Path $BackupRoot $stamp
    Ensure-Directory $backupDir

    foreach ($relativePath in $LocalSettings) {
        $source = Join-Path $Root $relativePath
        if (Test-Path -LiteralPath $source) {
            $target = Join-Path $backupDir $relativePath
            Ensure-Directory (Split-Path -Parent $target)
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }

    return $backupDir
}

function Restore-LocalSettings {
    param([string]$BackupDir)

    foreach ($relativePath in $LocalSettings) {
        $source = Join-Path $BackupDir $relativePath
        if (Test-Path -LiteralPath $source) {
            $target = Join-Path $Root $relativePath
            Ensure-Directory (Split-Path -Parent $target)
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

function Get-GitCommand {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        return $null
    }
    return $cmd.Source
}

function Get-RemoteSha {
    $apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/commits/$Branch"
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -Headers @{"User-Agent" = "Master-Report-Updater"} -TimeoutSec 30
        return [string]$response.sha
    } catch {
        Write-Log "Не удалось проверить последнюю версию через GitHub API: $($_.Exception.Message)"
        return $null
    }
}

function Update-WithGit {
    param([string]$Git)

    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        return $false
    }

    Push-Location $Root
    try {
        $remoteUrl = & $Git remote get-url origin 2>$null
        if (-not $remoteUrl) {
            & $Git remote add origin "https://github.com/$RepoOwner/$RepoName.git" | Out-Null
        }

        Write-Log "Проверяю обновления через Git..."
        & $Git fetch origin $Branch --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "git fetch завершился с кодом $LASTEXITCODE"
        }

        $localSha = (& $Git rev-parse HEAD).Trim()
        $remoteSha = (& $Git rev-parse "origin/$Branch").Trim()
        if ($localSha -eq $remoteSha) {
            Write-Log "Новых версий нет. Текущая версия: $localSha"
            return $true
        }

        $backupDir = Backup-LocalSettings
        Write-Log "Найдена новая версия: $remoteSha. Backup настроек: $backupDir"
        & $Git pull --ff-only origin $Branch
        if ($LASTEXITCODE -ne 0) {
            throw "git pull --ff-only завершился с кодом $LASTEXITCODE. Проверьте локальные изменения."
        }
        Restore-LocalSettings $backupDir
        Write-Log "Обновление через Git выполнено. Настройки возвращены."
        return $true
    } finally {
        Pop-Location
    }
}

function Update-WithZip {
    $remoteSha = Get-RemoteSha
    $lastShaFile = Join-Path $StateDir "last_sha.txt"
    if ($remoteSha -and (Test-Path -LiteralPath $lastShaFile)) {
        $currentSha = (Get-Content -LiteralPath $lastShaFile -Raw).Trim()
        if ($currentSha -eq $remoteSha) {
            Write-Log "Новых версий нет. Текущая версия: $currentSha"
            return
        }
    }

    $backupDir = Backup-LocalSettings
    $tempDir = Join-Path $env:TEMP ("master_report_update_" + [guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempDir "source.zip"
    Ensure-Directory $tempDir

    try {
        $zipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
        Write-Log "Git не найден или папка без .git. Скачиваю zip из GitHub..."
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
        Expand-Archive -LiteralPath $zipPath -DestinationPath $tempDir -Force
        $sourceRoot = Get-ChildItem -LiteralPath $tempDir -Directory | Where-Object { $_.Name -like "$RepoName-*" } | Select-Object -First 1
        if ($null -eq $sourceRoot) {
            throw "Не найдена распакованная папка проекта."
        }

        $items = @(
            "APP",
            "docs",
            "tests",
            "tools",
            "requirements.txt",
            "requirements-dev.txt",
            "README.md",
            "pyproject.toml",
            "ЗАПУСК.bat",
            "ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat"
        )
        foreach ($item in $items) {
            $source = Join-Path $sourceRoot.FullName $item
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination (Join-Path $Root $item) -Recurse -Force
            }
        }

        Restore-LocalSettings $backupDir
        Ensure-Directory $StateDir
        if ($remoteSha) {
            Set-Content -LiteralPath $lastShaFile -Value $remoteSha -Encoding UTF8
        }
        Write-Log "Обновление через zip выполнено. Настройки возвращены."
    } finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force
        }
    }
}

function Update-Dependencies {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $requirements = Join-Path $Root "requirements.txt"
    if ((Test-Path -LiteralPath $venvPython) -and (Test-Path -LiteralPath $requirements)) {
        Write-Log "Обновляю зависимости в локальном .venv..."
        & $venvPython -m pip install -r $requirements | Tee-Object -FilePath $LogFile -Append
        if ($LASTEXITCODE -ne 0) {
            throw "pip install завершился с кодом $LASTEXITCODE"
        }
    }
}

Set-Content -Path $LogFile -Value "" -Encoding UTF8
Write-Log "Master Report updater started."
Write-Log "Project folder: $Root"

$git = Get-GitCommand
$updatedWithGit = $false
if ($git) {
    $updatedWithGit = Update-WithGit $git
}
if (-not $updatedWithGit) {
    Update-WithZip
}

Update-Dependencies

if ($Launch) {
    $launcher = Join-Path $Root "ЗАПУСК.bat"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Не найден ЗАПУСК.bat"
    }
    Write-Log "Запускаю приложение..."
    Start-Process -FilePath $launcher -WorkingDirectory $Root
}

Write-Log "Updater finished successfully."

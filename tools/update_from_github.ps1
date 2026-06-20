param(
    [string]$RepoOwner = "sunil123456897",
    [string]$RepoName = "Exel_otchet",
    [string]$Branch = "main",
    # Pin a specific commit SHA for integrity verification. When set,
    # the updater ABORTS if the fetched commit does not match the pin —
    # this stops a compromised repository (or MITM with a valid TLS
    # cert) from pushing arbitrary code to user PCs. Empty = accept
    # branch HEAD (LESS SECURE — only use during development).
    # Bumping the pin requires manual review of the diff between the
    # old and new SHA on github.com/<owner>/<repo>/compare/<old>...<new>.
    [string]$PinnedCommitSha = "",
    [switch]$Launch
)

$ErrorActionPreference = "Stop"

$env:PIP_NO_KEYRING = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_INPUT = "1"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Warning "Could not force TLS 1.2 for GitHub downloads: $($_.Exception.Message)"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogFile = Join-Path $Root "update_log.txt"
$StateDir = Join-Path $Root ".update_state"
$BackupRoot = Join-Path $Root ".update_backups"
$LocalSettings = @("APP\config.yaml", "APP\employees.yaml")
$LocalData = @(
    "APP\cache.db",
    "APP\cache.db-wal",
    "APP\cache.db-shm",
    "APP\runtime_state.json"
)
$ProtectedUpdatePaths = $LocalSettings + $LocalData + @(
    "APP\output",
    "REPORTS",
    "РСЧ",
    "рсч всех",
    "Master_Report.xlsx"
)
$UpdateItems = @(
    "APP\core",
    "APP\main.py",
    "APP\headless_run.py",
    "APP\db_schema.sql",
    "APP\config.example.yaml",
    "APP\migrations",
    "requirements.txt",
    "ЗАПУСК.bat",
    "ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat",
    "tools\update_from_github.ps1"
)

function Get-GitHubToken {
    $tokenFile = Join-Path $Root ".github_token"
    if (Test-Path -LiteralPath $tokenFile) {
        $token = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
        if ($token) { return $token }
    }
    $envToken = $env:GITHUB_TOKEN
    if ($envToken) { return $envToken }
    return $null
}

function Get-GitHubHeaders {
    param([string]$Token)
    $headers = @{"User-Agent" = "Master-Report-Updater"}
    if ($Token) {
        $headers["Authorization"] = "token $Token"
    }
    return $headers
}

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

function Normalize-RelativePath {
    param([string]$Path)
    return (($Path -replace "/", "\").TrimEnd("\")).ToLowerInvariant()
}

function Test-IsSameOrChildPath {
    param(
        [string]$Candidate,
        [string]$Parent
    )

    $candidateNorm = Normalize-RelativePath $Candidate
    $parentNorm = Normalize-RelativePath $Parent
    return $candidateNorm -eq $parentNorm -or $candidateNorm.StartsWith($parentNorm + "\")
}

function Test-IsProtectedByUpdateItem {
    param(
        [string]$ProtectedPath,
        [string]$UpdateItem
    )

    return (Test-IsSameOrChildPath $ProtectedPath $UpdateItem) -or (Test-IsSameOrChildPath $UpdateItem $ProtectedPath)
}

function Assert-UpdatePolicy {
    foreach ($item in $UpdateItems) {
        $normalized = Normalize-RelativePath $item
        if ($normalized -in @(".", "app", "reports", "рсч", "рсч всех")) {
            throw "Небезопасный update allowlist item: $item"
        }

        foreach ($protectedPath in $ProtectedUpdatePaths) {
            if (Test-IsProtectedByUpdateItem $protectedPath $item) {
                throw "Update item '$item' пересекается с локальными данными '$protectedPath'"
            }
        }
    }
}

function Backup-LocalFiles {
    param([string[]]$RelativePaths)

    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDir = Join-Path $BackupRoot $stamp
    Ensure-Directory $backupDir

    foreach ($relativePath in $RelativePaths) {
        $source = Join-Path $Root $relativePath
        if (Test-Path -LiteralPath $source) {
            $target = Join-Path $backupDir $relativePath
            Ensure-Directory (Split-Path -Parent $target)
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }

    return $backupDir
}

function Restore-LocalFiles {
    param(
        [string]$BackupDir,
        [string[]]$RelativePaths
    )

    foreach ($relativePath in $RelativePaths) {
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
    param([string]$Token)
    $apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/commits/$Branch"
    try {
        $headers = Get-GitHubHeaders $Token
        $response = Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 30
        return [string]$response.sha
    } catch {
        Write-Log "Не удалось проверить последнюю версию через GitHub API: $($_.Exception.Message)"
        return $null
    }
}

function Get-InstalledSha {
    param([string]$FallbackSha)

    $lastShaFile = Join-Path $StateDir "last_sha.txt"
    if (Test-Path -LiteralPath $lastShaFile) {
        $storedSha = (Get-Content -LiteralPath $lastShaFile -Raw).Trim()
        if ($storedSha) {
            return $storedSha
        }
    }

    return $FallbackSha
}

function Assert-PinnedCommit {
    param([string]$ResolvedSha)

    # Integrity gate: refuse to apply an update whose commit SHA does not
    # match the operator-pinned value. Without this check, a compromised
    # GitHub repo (or a TLS-MITM with a valid cert) could push arbitrary
    # code to every user PC running ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat.
    if (-not $PinnedCommitSha) {
        Write-Warning "PinnedCommitSha не задан — обновление из ветки '$Branch' без проверки целостности. Задайте -PinnedCommitSha для защиты от компрометации репозитория."
        return
    }
    if ([string]::IsNullOrWhiteSpace($ResolvedSha)) {
        throw "Не удалось определить SHA загруженного коммита. Обновление отменено (нет целостности)."
    }
    $resolvedNorm = $ResolvedSha.Trim().ToLowerInvariant()
    $pinnedNorm = $PinnedCommitSha.Trim().ToLowerInvariant()
    if ($resolvedNorm -ne $pinnedNorm) {
        throw "Целостность обновления НЕ подтверждена: полученный commit '$resolvedNorm' не совпадает с закреплённым '$pinnedNorm'. Обновление ОТМЕНЕНО. Для обновления пина вручную проверьте diff на github.com/$RepoOwner/$RepoName/compare/$pinnedNorm...$resolvedNorm и обновите -PinnedCommitSha."
    }
}

function Copy-UpdateItems {
    param([string]$SourceRoot)

    foreach ($item in $UpdateItems) {
        $source = Join-Path $SourceRoot $item
        if (-not (Test-Path -LiteralPath $source)) {
            Write-Log "Пропускаю отсутствующий файл обновления: $item"
            continue
        }

        $target = Join-Path $Root $item
        if (Test-Path -LiteralPath $source -PathType Container) {
            Ensure-Directory $target
            Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $target -Recurse -Force
        } else {
            Ensure-Directory (Split-Path -Parent $target)
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

function Expand-GitArchive {
    param(
        [string]$Git,
        [string]$Treeish,
        [string]$Destination
    )

    Ensure-Directory $Destination
    $archivePath = Join-Path $Destination "update.tar"
    $normalizedItems = $UpdateItems | ForEach-Object { $_ -replace "\\", "/" }

    & $Git archive --format=tar --output=$archivePath $Treeish -- $normalizedItems
    if ($LASTEXITCODE -ne 0) {
        throw "git archive завершился с кодом $LASTEXITCODE"
    }

    tar -xf $archivePath -C $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "tar завершился с кодом $LASTEXITCODE"
    }
}

function Update-WithGit {
    param([string]$Git, [string]$Token)

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
        # Pass token via http.extraHeader instead of embedding in the
        # remote URL to avoid leaking it in git logs, error messages,
        # and process listings.
        if ($Token) {
            $env:GIT_ASKPASS = ""
            $env:GIT_TERMINAL_PROMPT = "0"
            & $Git -c "http.extraHeader=Authorization: token $Token" fetch origin $Branch --quiet
        } else {
            & $Git fetch origin $Branch --quiet
        }
        if ($LASTEXITCODE -ne 0) {
            throw "git fetch завершился с кодом $LASTEXITCODE"
        }

        $headSha = (& $Git rev-parse HEAD).Trim()
        $localSha = Get-InstalledSha $headSha
        $remoteSha = (& $Git rev-parse "origin/$Branch").Trim()
        Assert-PinnedCommit $remoteSha
        if ($localSha -eq $remoteSha) {
            Write-Log "Новых версий нет. Текущая версия: $localSha"
            return $true
        }

        $backupDir = Backup-LocalFiles ($LocalSettings + $LocalData)
        Write-Log "Найдена новая версия: $remoteSha. Backup локальных настроек/БД: $backupDir"

        $tempDir = Join-Path $env:TEMP ("master_report_git_update_" + [guid]::NewGuid().ToString("N"))
        try {
            Expand-GitArchive $Git "origin/$Branch" $tempDir
            Copy-UpdateItems $tempDir
        } finally {
            if (Test-Path -LiteralPath $tempDir) {
                Remove-Item -LiteralPath $tempDir -Recurse -Force
            }
        }

        Restore-LocalFiles $backupDir ($LocalSettings + $LocalData)
        Ensure-Directory $StateDir
        Set-Content -LiteralPath (Join-Path $StateDir "last_sha.txt") -Value $remoteSha -Encoding UTF8
        Write-Log "Минимальное обновление через Git выполнено. Локальные настройки/БД возвращены."
        return $true
    } catch {
        Write-Log "WARNING: Git update failed: $($_.Exception.Message). Falling back to snapshot update..."
        return $false
    } finally {
        Pop-Location
    }
}

function Update-WithGitSnapshot {
    param([string]$Git)

    $tempRepo = Join-Path $env:TEMP ("master_report_git_snapshot_repo_" + [guid]::NewGuid().ToString("N"))
    $tempArchive = Join-Path $env:TEMP ("master_report_git_snapshot_update_" + [guid]::NewGuid().ToString("N"))
    $pushed = $false

    try {
        Ensure-Directory $tempRepo
        Ensure-Directory $tempArchive
        Push-Location $tempRepo
        $pushed = $true

        try {
            & $Git init --quiet
            if ($LASTEXITCODE -ne 0) {
                throw "git init завершился с кодом $LASTEXITCODE"
            }

            & $Git remote add origin "https://github.com/$RepoOwner/$RepoName.git"
            if ($LASTEXITCODE -ne 0) {
                throw "git remote add завершился с кодом $LASTEXITCODE"
            }

            Write-Log "Папка без .git. Скачиваю минимальный snapshot через Git..."
            & $Git fetch --depth=1 origin $Branch --quiet
            if ($LASTEXITCODE -ne 0) {
                throw "git fetch snapshot завершился с кодом $LASTEXITCODE"
            }

            $remoteSha = (& $Git rev-parse FETCH_HEAD).Trim()
            Assert-PinnedCommit $remoteSha
            $localSha = Get-InstalledSha ""
            if ($localSha -eq $remoteSha) {
                Write-Log "Новых версий нет. Текущая версия: $localSha"
                return $true
            }

            $backupDir = Backup-LocalFiles ($LocalSettings + $LocalData)
            Write-Log "Найдена новая версия: $remoteSha. Backup локальных настроек/БД: $backupDir"

            Expand-GitArchive $Git "FETCH_HEAD" $tempArchive
            Copy-UpdateItems $tempArchive
            Restore-LocalFiles $backupDir ($LocalSettings + $LocalData)
            Ensure-Directory $StateDir
            Set-Content -LiteralPath (Join-Path $StateDir "last_sha.txt") -Value $remoteSha -Encoding UTF8
            Write-Log "Минимальное обновление через Git snapshot выполнено. Локальные настройки/БД возвращены."
            return $true
        } catch {
            Write-Log "WARNING: Git snapshot update failed: $($_.Exception.Message). Falling back to zip update..."
            return $false
        }
    } finally {
        if ($pushed) {
            Pop-Location
        }
        if (Test-Path -LiteralPath $tempArchive) {
            Remove-Item -LiteralPath $tempArchive -Recurse -Force
        }
        if (Test-Path -LiteralPath $tempRepo) {
            Remove-Item -LiteralPath $tempRepo -Recurse -Force
        }
    }
}

function Update-WithZip {
    param([string]$Token)
    $remoteSha = Get-RemoteSha $Token
    Assert-PinnedCommit $remoteSha
    $lastShaFile = Join-Path $StateDir "last_sha.txt"
    if ($remoteSha -and (Test-Path -LiteralPath $lastShaFile)) {
        $currentSha = (Get-Content -LiteralPath $lastShaFile -Raw).Trim()
        if ($currentSha -eq $remoteSha) {
            Write-Log "Новых версий нет. Текущая версия: $currentSha"
            return
        }
    }

    $backupDir = Backup-LocalFiles ($LocalSettings + $LocalData)
    $tempDir = Join-Path $env:TEMP ("master_report_update_" + [guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempDir "source.zip"
    Ensure-Directory $tempDir

    try {
        if ($Token) {
            $zipUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/zipball/$Branch"
            $headers = Get-GitHubHeaders $Token
            $headers["Accept"] = "application/vnd.github+json"
        } else {
            $zipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
            $headers = Get-GitHubHeaders $Token
        }
        Write-Log "Git не найден или папка без .git. Скачиваю zip из GitHub..."
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 120 -Headers $headers
        Expand-Archive -LiteralPath $zipPath -DestinationPath $tempDir -Force
        $sourceRoot = Get-ChildItem -LiteralPath $tempDir -Directory | Where-Object { $_.Name -like "$RepoName-*" -or $_.Name -like "$RepoOwner-$RepoName-*" } | Select-Object -First 1
        if ($null -eq $sourceRoot) {
            throw "Не найдена распакованная папка проекта."
        }

        Copy-UpdateItems $sourceRoot.FullName

        Restore-LocalFiles $backupDir ($LocalSettings + $LocalData)
        Ensure-Directory $StateDir
        if ($remoteSha) {
            Set-Content -LiteralPath $lastShaFile -Value $remoteSha -Encoding UTF8
        }
        Write-Log "Минимальное обновление через zip выполнено. Локальные настройки/БД возвращены."
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
        $size = (Get-Item -LiteralPath $venvPython).Length
        $valid = $false
        if ($size -gt 10000) {
            $null = & $venvPython --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                $valid = $true
            }
        }
        if ($valid) {
            Write-Log "Обновляю зависимости в локальном .venv..."
            & $venvPython -m pip install -r $requirements | Tee-Object -FilePath $LogFile -Append
            if ($LASTEXITCODE -ne 0) {
                throw "pip install завершился с кодом $LASTEXITCODE"
            }
        } else {
            Write-Warning "Локальное виртуальное окружение .venv неисправно. Пропускаю обновление зависимостей в апдейтере. ЗАПУСК.bat автоматически пересоздаст окружение."
        }
    }
}

Set-Content -Path $LogFile -Value "" -Encoding UTF8
Write-Log "Master Report updater started."
Write-Log "Project folder: $Root"
Assert-UpdatePolicy

$gitHubToken = Get-GitHubToken
if ($gitHubToken) {
    Write-Log "GitHub токен найден. Используется авторизованный доступ."
} else {
    Write-Log "GitHub токен не найден. Попытка анонимного доступа..."
}

$git = Get-GitCommand
$updatedWithGit = $false
if ($git) {
    $updatedWithGit = Update-WithGit $git
    if (-not $updatedWithGit) {
        $updatedWithGit = Update-WithGitSnapshot $git
    }
}
if (-not $updatedWithGit) {
    Update-WithZip $gitHubToken
}

Update-Dependencies

if ($Launch) {
    $launcher = Join-Path $Root "ЗАПУСК.bat"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Не найден ЗАПУСК.bat"
    }
    Write-Log "Запускаю приложение..."
    Start-Process -FilePath $launcher -ArgumentList "/nopause" -WorkingDirectory $Root
}

Write-Log "Updater finished successfully."

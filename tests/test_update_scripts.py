from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_update_launcher_exists_and_calls_powershell_script() -> None:
    launcher = ROOT / "ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat"

    text = launcher.read_text(encoding="utf-8")

    assert "tools\\update_from_github.ps1" in text
    assert "-Launch" in text


def test_update_script_preserves_local_config_files() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8")

    assert "APP\\config.yaml" in text
    assert "APP\\employees.yaml" in text
    assert "Backup-LocalFiles" in text
    assert "Restore-LocalFiles" in text


def test_update_script_preserves_local_database_files() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8")

    assert "APP\\cache.db" in text
    assert "APP\\cache.db-wal" in text
    assert "APP\\cache.db-shm" in text
    assert "APP\\runtime_state.json" in text
    assert "$ProtectedUpdatePaths" in text
    assert "Assert-UpdatePolicy" in text


def test_update_script_does_not_use_destructive_git_reset() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8").lower()

    assert "reset --hard" not in text
    assert "clean -fd" not in text


def test_update_script_uses_minimal_runtime_allowlist() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8")

    assert "$UpdateItems = @(" in text
    assert '"APP\\core"' in text
    assert '"APP\\main.py"' in text
    assert '"APP\\headless_run.py"' in text
    assert '"APP\\db_schema.sql"' in text
    assert '"requirements.txt"' in text
    assert '"tools\\update_from_github.ps1"' in text

    assert '"APP"' not in text
    assert '"docs"' not in text
    assert '"tests"' not in text
    assert '"README.md"' not in text
    assert '"pyproject.toml"' not in text
    assert '"requirements-dev.txt"' not in text


def test_update_script_does_not_pull_or_copy_whole_repo() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8").lower()

    assert "git pull" not in text
    assert "copy-updateitems" in text
    assert "git archive" in text


def test_update_script_tracks_installed_sha_without_moving_git_head() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8")

    assert "function Get-InstalledSha" in text
    assert "$headSha = (& $Git rev-parse HEAD).Trim()" in text
    assert "$localSha = Get-InstalledSha $headSha" in text
    assert 'Join-Path $StateDir "last_sha.txt"' in text


def test_update_script_protects_user_data_locations() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8")

    for protected_path in (
        "APP\\output",
        "REPORTS",
        "РСЧ",
        "рсч всех",
        "Master_Report.xlsx",
    ):
        assert protected_path in text

    assert "Test-IsProtectedByUpdateItem" in text
    assert "пересекается с локальными данными" in text

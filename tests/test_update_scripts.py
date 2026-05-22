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
    assert "Backup-LocalSettings" in text
    assert "Restore-LocalSettings" in text


def test_update_script_does_not_use_destructive_git_reset() -> None:
    script = ROOT / "tools" / "update_from_github.ps1"

    text = script.read_text(encoding="utf-8").lower()

    assert "reset --hard" not in text
    assert "clean -fd" not in text

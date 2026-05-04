import importlib.util
import sys
from pathlib import Path


def _load_runner():
    path = Path(__file__).parents[1] / "tools" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("run_tests_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pytest_args_adds_stable_windows_defaults():
    runner = _load_runner()

    args = runner._pytest_args([])

    assert args[:2] == ["tests", "-q"]
    assert ["--basetemp", "tmp_pytest_safe"] == args[2:4]
    assert "-o" in args
    assert "addopts=" in args
    assert args.count("-p") == 2
    assert "no:cacheprovider" in args
    assert "pytest_mock" in args


def test_pytest_args_preserves_explicit_basetemp_and_plugins():
    runner = _load_runner()

    args = runner._pytest_args(
        [
            "tests/test_view_models.py",
            "--basetemp=custom-temp",
            "-p",
            "no:cacheprovider",
            "-ppytest_mock",
        ]
    )

    assert args.count("--basetemp") == 0
    assert "--basetemp=custom-temp" in args
    assert args.count("no:cacheprovider") == 1
    assert args.count("-ppytest_mock") == 1


def test_main_sets_environment_and_delegates_to_pytest(monkeypatch):
    runner = _load_runner()
    captured = {}

    class FakePytest:
        @staticmethod
        def main(args):
            captured["args"] = args
            return 7

    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    monkeypatch.setitem(sys.modules, "pytest", FakePytest)
    monkeypatch.setattr(
        runner,
        "_patch_missing_overlapped",
        lambda: captured.setdefault("overlapped", True),
    )
    monkeypatch.setattr(
        runner,
        "_patch_windows_mkdir_mode",
        lambda: captured.setdefault("mkdir", True),
    )

    result = runner.main(["tests/test_run_tests_tool.py", "-q"])

    assert result == 7
    assert captured["overlapped"] is True
    assert captured["mkdir"] is True
    assert captured["args"][:2] == ["tests/test_run_tests_tool.py", "-q"]
    assert "tmp_pytest_safe" in captured["args"]

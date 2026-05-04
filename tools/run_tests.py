from __future__ import annotations

import os
import sys
import types
from collections.abc import Sequence


def _patch_missing_overlapped() -> None:
    if os.name != "nt":
        return

    try:
        __import__("_overlapped")
    except (ImportError, OSError):
        sys.modules.setdefault("_overlapped", types.ModuleType("_overlapped"))


def _patch_windows_mkdir_mode() -> None:
    if os.name != "nt":
        return

    original_mkdir = os.mkdir

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if dir_fd is None:
            return original_mkdir(path, 0o777)
        return original_mkdir(path, 0o777, dir_fd=dir_fd)

    os.mkdir = mkdir


def _has_option(args: Sequence[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def _has_pytest_plugin(args: Sequence[str], plugin_name: str) -> bool:
    for index, arg in enumerate(args):
        if arg == "-p" and index + 1 < len(args) and args[index + 1] == plugin_name:
            return True
        if arg == f"-p{plugin_name}":
            return True
    return False


def _pytest_args(argv: Sequence[str]) -> list[str]:
    args = list(argv) if argv else ["tests", "-q"]

    if not _has_option(args, "--basetemp"):
        args.extend(["--basetemp", "tmp_pytest_safe"])
    if "-o" not in args:
        args.extend(["-o", "addopts="])
    if not _has_pytest_plugin(args, "no:cacheprovider"):
        args.extend(["-p", "no:cacheprovider"])
    if not _has_pytest_plugin(args, "pytest_mock"):
        args.extend(["-p", "pytest_mock"])

    return args


def main(argv: Sequence[str] | None = None) -> int:
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    _patch_missing_overlapped()
    _patch_windows_mkdir_mode()

    import pytest

    return pytest.main(_pytest_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())

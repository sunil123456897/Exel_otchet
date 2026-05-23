import os
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class PathInfo:
    label: str
    path: Path | None
    exists: bool
    kind: str
    mtime: str = "-"
    size: str = "-"


@dataclass(frozen=True)
class DiagnosticItem:
    label: str
    status: str
    detail: str
    path: Path | None = None


@dataclass(frozen=True)
class RuntimeResult:
    label: str
    ok: bool
    message: str
    path: Path | None = None
    rows: int | None = None
    created_at: datetime | None = None


STATUS_MARKERS = {
    "ok": "✅ OK",
    "warning": "⚠️ Внимание",
    "error": "❌ Ошибка",
}


def format_file_size(path: Path | None) -> str:
    if not path:
        return "-"
    try:
        size = path.stat().st_size
    except OSError:
        return "-"

    units = ("B", "KB", "MB", "GB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.1f} {unit}"


def format_mtime(path: Path | None) -> str:
    if not path:
        return "-"
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return "-"
    return stamp.strftime("%d.%m.%Y %H:%M")


def find_latest_file(directory: Path | str | None, patterns: Iterable[str]) -> Path | None:
    if not directory:
        return None
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return None

    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(path for path in root.glob(pattern) if path.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def safe_open_existing_path(
    path: Path | str | None,
    opener: Callable[[str], object],
    on_missing: Callable[[str], object] | None = None,
) -> bool:
    if not path:
        if on_missing:
            on_missing("Путь не задан")
        return False

    resolved = Path(path)
    if not resolved.exists():
        if on_missing:
            on_missing(f"Путь не найден: {resolved}")
        return False

    opener(str(resolved))
    return True


def status_text(status: str) -> str:
    return STATUS_MARKERS.get(status, f"❌ {status}")


def load_runtime_results(state_path: Path | str) -> list[RuntimeResult]:
    path = Path(state_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []

    results: list[RuntimeResult] = []
    for item in raw[:10]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        message = str(item.get("message") or "").strip()
        if not label or not message:
            continue
        created_at = None
        raw_created = item.get("created_at")
        if isinstance(raw_created, str) and raw_created:
            try:
                created_at = datetime.fromisoformat(raw_created)
            except ValueError:
                created_at = None
        raw_path = item.get("path")
        raw_rows = item.get("rows")
        rows = raw_rows if isinstance(raw_rows, int) else None
        results.append(
            RuntimeResult(
                label=label,
                ok=bool(item.get("ok")),
                message=message,
                path=Path(str(raw_path)) if raw_path else None,
                rows=rows,
                created_at=created_at,
            )
        )
    return results


def save_runtime_results(
    state_path: Path | str,
    results: Iterable[RuntimeResult],
) -> None:
    path = Path(state_path)
    payload = []
    for result in list(results)[:10]:
        payload.append(
            {
                "label": result.label,
                "ok": result.ok,
                "message": result.message,
                "path": str(result.path) if result.path else "",
                "rows": result.rows,
                "created_at": result.created_at.isoformat()
                if result.created_at
                else "",
            }
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return


def build_diagnostic_summary(
    diagnostics: Iterable[DiagnosticItem | tuple[str, str, str, Path | None]],
    results: Iterable[RuntimeResult],
    log_errors: Iterable[str],
) -> str:
    lines = ["Диагностика Master-Report", ""]
    lines.append("Система:")
    for item in diagnostics:
        if isinstance(item, DiagnosticItem):
            label = item.label
            state = status_text(item.status)
            detail = item.detail
            path = item.path
        else:
            label, state, detail, path = item
        suffix = f" | {path}" if path else ""
        lines.append(f"- {label}: {state} | {detail}{suffix}")

    lines.extend(["", "Последние результаты:"])
    result_list = list(results)
    if result_list:
        for result in result_list[:10]:
            state = "✅ успех" if result.ok else "❌ ошибка"
            time_text = (
                result.created_at.strftime("%d.%m.%Y %H:%M")
                if result.created_at
                else "-"
            )
            path_text = f" | {result.path}" if result.path else ""
            lines.append(f"- {time_text} | {result.label}: {state} | {result.message}{path_text}")
    else:
        lines.append("- нет сохраненных результатов")

    lines.extend(["", "Последние ошибки логов:"])
    errors = list(log_errors)
    if errors:
        lines.extend(f"- {line}" for line in errors)
    else:
        lines.append("- не найдены")
    return "\n".join(lines)


def describe_path(label: str, path: Path | str | None, kind: str = "file") -> PathInfo:
    resolved = Path(path) if path else None
    exists = bool(resolved and resolved.exists())
    return PathInfo(
        label=label,
        path=resolved,
        exists=exists,
        kind=kind,
        mtime=format_mtime(resolved) if exists else "-",
        size=format_file_size(resolved) if exists and resolved.is_file() else "-",
    )


def _resolve_config_path(config_controller, value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute() or str(value).startswith("\\\\"):
        return path
    resolver = getattr(config_controller, "resolve_path", None)
    if callable(resolver):
        return Path(resolver(str(value)))
    config_path = Path(getattr(config_controller, "config_path", "."))
    return (config_path.parent / path).resolve()


def _config(config_controller) -> dict:
    raw = getattr(config_controller, "config", {})
    return raw if isinstance(raw, dict) else {}


def collect_report_paths(config_controller, app_root: Path | None = None) -> list[PathInfo]:
    cfg = _config(config_controller)
    app_root = app_root or Path(getattr(config_controller, "config_path", ".")).parent
    paths_cfg = cfg.get("paths", {}) if isinstance(cfg.get("paths"), dict) else {}
    rsch_cfg = cfg.get("rsch", {}) if isinstance(cfg.get("rsch"), dict) else {}
    curators_cfg = cfg.get("curators", {}) if isinstance(cfg.get("curators"), dict) else {}

    master_path = _resolve_config_path(
        config_controller, paths_cfg.get("master_file", "../Master_Report.xlsx")
    )
    rsch_dir = _resolve_config_path(config_controller, rsch_cfg.get("last_output_dir"))
    backup_dir = _resolve_config_path(config_controller, paths_cfg.get("archive_dir", "../backups"))
    benchmarks_dir = app_root.parent / "benchmarks"

    items = [
        describe_path("Master_Report.xlsx", master_path),
        describe_path(
            "boris_report.xlsx",
            _resolve_config_path(
                config_controller,
                curators_cfg.get("boris", {}).get("output_path")
                if isinstance(curators_cfg.get("boris"), dict)
                else None,
            ),
        ),
        describe_path(
            "ivan_report.xlsx",
            _resolve_config_path(
                config_controller,
                curators_cfg.get("ivan", {}).get("output_path")
                if isinstance(curators_cfg.get("ivan"), dict)
                else None,
            ),
        ),
        describe_path(
            "Последний РСЧ",
            find_latest_file(rsch_dir, ("РСЧ_отчет*.xlsx", "РСЧ*.xlsx")),
        ),
        describe_path(
            "Последняя сверка",
            find_latest_file(rsch_dir, ("Отчет_расхождений*.xlsx",)),
        ),
        describe_path("Backup", backup_dir, kind="folder"),
        describe_path(
            "Последний benchmark",
            find_latest_file(benchmarks_dir, ("timing_*.md", "timing_*.json")),
        ),
    ]
    return items


def collect_settings_lines(config_controller) -> list[str]:
    cfg = _config(config_controller)
    paths_cfg = cfg.get("paths", {}) if isinstance(cfg.get("paths"), dict) else {}
    network_cfg = cfg.get("network", {}) if isinstance(cfg.get("network"), dict) else {}
    performance_cfg = cfg.get("performance", {}) if isinstance(cfg.get("performance"), dict) else {}
    backup_cfg = cfg.get("backup", {}) if isinstance(cfg.get("backup"), dict) else {}
    rsch_cfg = cfg.get("rsch", {}) if isinstance(cfg.get("rsch"), dict) else {}

    drive_letters = network_cfg.get("drive_letters", [])
    if isinstance(drive_letters, list):
        drive_text = ", ".join(str(item) for item in drive_letters) or "-"
    else:
        drive_text = str(drive_letters)

    return [
        f"performance.max_workers: {performance_cfg.get('max_workers') or 'auto'}",
        f"backup.excel_keep: {backup_cfg.get('excel_keep', 10)}",
        f"paths.master_file: {paths_cfg.get('master_file', '-')}",
        f"paths.archive_dir: {paths_cfg.get('archive_dir', '-')}",
        f"rsch.last_output_dir: {rsch_cfg.get('last_output_dir', '-')}",
        f"network.drive_letters: {drive_text}",
    ]


def read_recent_log_errors(log_paths: Iterable[Path | str], limit: int = 5) -> list[str]:
    lines: list[str] = []
    for raw_path in log_paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                upper = line.upper()
                if "ERROR" in upper or "CRITICAL" in upper or "ОШИБ" in upper:
                    lines.append(line.strip())
        except OSError:
            continue
    return lines[-limit:]


def run_light_diagnostics(
    config_controller,
    app_root: Path | None = None,
    include_network: bool = True,
) -> list[DiagnosticItem]:
    cfg = _config(config_controller)
    app_root = app_root or Path(getattr(config_controller, "config_path", ".")).parent
    repo_root = app_root.parent
    paths_cfg = cfg.get("paths", {}) if isinstance(cfg.get("paths"), dict) else {}
    db_cfg = cfg.get("database", {}) if isinstance(cfg.get("database"), dict) else {}
    network_cfg = cfg.get("network", {}) if isinstance(cfg.get("network"), dict) else {}

    config_path = Path(getattr(config_controller, "config_path", app_root / "config.yaml"))
    employees_path = Path(getattr(config_controller, "employees_path", app_root / "employees.yaml"))
    db_path = _resolve_config_path(config_controller, db_cfg.get("path", "cache.db"))
    backup_path = _resolve_config_path(config_controller, paths_cfg.get("archive_dir", "../backups"))
    master_path = _resolve_config_path(config_controller, paths_cfg.get("master_file", "../Master_Report.xlsx"))

    diagnostics = [
        DiagnosticItem("Python", "ok", sys.version.split()[0], Path(sys.executable)),
        DiagnosticItem(
            ".venv",
            "ok" if Path(sys.prefix).name == ".venv" else "warning",
            str(sys.prefix),
            Path(sys.prefix),
        ),
        _path_diagnostic("config.yaml", config_path, require_file=True),
        _path_diagnostic("employees.yaml", employees_path, require_file=True),
        _writable_diagnostic("cache.db", db_path),
        _writable_diagnostic("Master output", master_path.parent if master_path else None, require_dir=True),
        _path_diagnostic(
            "Backup folder",
            backup_path,
            require_file=False,
            missing_status="warning",
        ),
        _path_diagnostic("Logs", repo_root / "startup_log.txt", require_file=True),
        _path_diagnostic(
            "Benchmarks",
            repo_root / "benchmarks",
            require_file=False,
            missing_status="warning",
        ),
    ]

    if include_network:
        source_roots = paths_cfg.get("source_roots") or [paths_cfg.get("source_root")]
        for raw in source_roots:
            if not raw:
                continue
            path = Path(str(raw))
            diagnostics.append(
                DiagnosticItem(
                    str(raw),
                    "ok" if path.exists() else "warning",
                    "доступен" if path.exists() else "не найден или недоступен",
                    path,
                )
            )

        for raw_letter in network_cfg.get("drive_letters", []):
            letter = str(raw_letter).strip().rstrip(":\\/")
            if not letter:
                continue
            root = Path(f"{letter}:\\")
            label = f"{letter}:\\"
            if any(item.label == label for item in diagnostics):
                continue
            diagnostics.append(
                DiagnosticItem(
                    label,
                    "ok" if root.exists() else "warning",
                    "доступен" if root.exists() else "не найден или недоступен",
                    root,
                )
            )
    return diagnostics


def _path_diagnostic(
    label: str,
    path: Path | None,
    require_file: bool,
    missing_status: str | None = None,
) -> DiagnosticItem:
    if not path:
        return DiagnosticItem(label, "error", "путь не задан", None)
    exists = path.is_file() if require_file else path.exists()
    if missing_status is None:
        missing_status = "error" if require_file else "warning"
    return DiagnosticItem(
        label,
        "ok" if exists else missing_status,
        "найден" if exists else "не найден",
        path,
    )


def _writable_diagnostic(
    label: str,
    path: Path | None,
    require_dir: bool = False,
) -> DiagnosticItem:
    if not path:
        return DiagnosticItem(label, "error", "путь не задан", None)
    target = path if require_dir else path.parent
    if not target.exists():
        return DiagnosticItem(label, "warning", f"папка не найдена: {target}", path)
    writable = os.access(target, os.W_OK)
    return DiagnosticItem(
        label,
        "ok" if writable else "error",
        "доступен для записи" if writable else "нет доступа на запись",
        path,
    )

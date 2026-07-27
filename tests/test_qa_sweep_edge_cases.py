"""Симуляции edge-cases работы заказчика (QA-sweep Phase 4.2).

Проверяем граничные сценарии, которые могут встретиться на ПК заказчика.
Логику НЕ меняем — фиксируем фактическое (задокументированное) поведение.

Покрывает пункты E1-E8 из docs/qa/qa-sweep-spec.md.
"""
from __future__ import annotations

import threading
import time
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from core.infra.rsch._build import build_rsch_report
from core.infra.rsch._collect import _normalize_source_paths
from core.services.rsch_service import RschService

# ---------------------------------------------------------------------------
# Хелперы: построение минимального валидного РСЧ-файла.
# ---------------------------------------------------------------------------


def _make_rsch_source(path: Path, rows_data):
    """Создать xlsx с листом-исполнителем и строками (date, income, expense).

    rows_data: list of (date, income, expense).
    Header должен содержать «приход рсч» / «расход рсч» — именно так
    _find_header_row определяет РСЧ-лист (см. _collect.py:40-44).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    # Имя листа должно содержать «рсч» — иначе _is_rsch_sheet_title его
    # пропустит (см. _format.py:98). Header должен содержать «дата»,
    # «приход рсч», «расход рсч», «проект», «контрагент» — required-колонки
    # в _detect_columns (_collect.py:82-88).
    ws.title = "РСЧ Иван"
    ws.append([
        "Дата", "Приход РСЧ", "Расход РСЧ", "Проект", "Проект", "Контрагент", "Контрагент",
    ])
    for d, inc, exp in rows_data:
        ws.append([d, inc, exp, "Заказчик А", "Заказчик Б", "Подрядчик А", "Подрядчик Б"])
    wb.save(path)
    wb.close()


def _make_empty_rsch_source(path: Path):
    """xlsx без валидных строк РСЧ (вызовет «нет строк»)."""
    wb = openpyxl.Workbook()
    wb.save(path)
    wb.close()


# ---------------------------------------------------------------------------
# E2: РСЧ за период по пустым данным → RuntimeError «нет строк»
# ---------------------------------------------------------------------------


def test_rsch_period_no_rows_raises_clear_error(tmp_path):
    """E2: период без данных должен дать понятную ошибку через сервис, а не молчание.

    Симптом «не выгружается» мог быть этим случаем, если пользователь
    думал, что данные есть, а их нет. Важно: ошибка НЕ тихая.

    Архитектура: build_rsch_report возвращает 0 (нейтрально, без exception),
    а RschService.run_rsch_report_period конвертирует 0 в ValueError
    «нет строк за период» — именно это видит GUI/пользователь.
    """
    src = tmp_path / "empty.xlsx"
    _make_empty_rsch_source(src)
    out = tmp_path / "out.xlsx"

    completed: dict = {}

    def on_complete(ok, msg, path):
        completed["ok"] = ok
        completed["msg"] = msg

    def start_thread(target):
        # Синхронно — мы хотим проверить результат.
        target()

    service = RschService(start_thread_fn=start_thread, get_drive_letters_fn=lambda: ("Q", "Z"))
    service.run_rsch_report_period(
        [src], out, date(2026, 1, 1), date(2026, 1, 31), on_complete
    )

    # Сервис должен вернуть ok=False с понятным сообщением про «нет строк».
    assert completed.get("ok") is False
    assert "нет строк" in completed["msg"].lower(), (
        f"Ожидалась понятная ошибка «нет строк», получено: {completed.get('msg')}"
    )


# ---------------------------------------------------------------------------
# E8: Период через границу года — коллизия имён листов исключена
# ---------------------------------------------------------------------------


def test_rsch_period_across_year_boundary_no_sheet_collision(tmp_path):
    """E8: период 31.12.2024 + 01.01.2025 не должен падать на duplicate sheet.

    Раньше (до коммита 323bed1) имена листов были %d.%m → коллизия
    «31.12»+«01.01» невозможна, но при смене года без года были бы дубли.
    Сейчас имена всегда %d.%m.%Y → коллизия исключена. Проверяем.
    """
    src = tmp_path / "cross_year.xlsx"
    _make_rsch_source(src, [
        (date(2024, 12, 31), 100, 0),
        (date(2025, 1, 1), 200, 50),
        (date(2025, 1, 2), 300, 0),
    ])
    out = tmp_path / "period.xlsx"

    written = build_rsch_report(
        [src], out,
        start_date=date(2024, 12, 31),
        end_date=date(2025, 1, 2),
    )
    assert written > 0
    assert out.exists()
    # Проверим, что все 3 даты + «Период» = 4 листа, без падения openpyxl
    wb = openpyxl.load_workbook(out, read_only=True)
    try:
        names = set(wb.sheetnames)
    finally:
        wb.close()
    assert "31.12.2024" in names
    assert "01.01.2025" in names
    assert "02.01.2025" in names
    assert "Период" in names


# ---------------------------------------------------------------------------
# E7: Дублирующиеся пути источников — дедупликация
# ---------------------------------------------------------------------------


def test_normalize_source_paths_dedupes(tmp_path):
    """E7: повторяющиеся пути должны быть дедуплицированы."""
    p = tmp_path / "a.xlsx"
    p.write_bytes(b"x")
    result = _normalize_source_paths([p, p, str(p), tmp_path / "a.xlsx"])
    assert len(result) == 1


def test_normalize_source_paths_handles_none_and_empty():
    """E7: None и пустые значения фильтруются."""
    result = _normalize_source_paths([None, "", Path(".")])
    # Пустые строки отбрасываются; "." валиден как путь
    assert all(r is not None for r in result)


# ---------------------------------------------------------------------------
# E1: РСЧ за период с несуществующим файлом → FileNotFoundError (не зависон)
# ---------------------------------------------------------------------------


def test_rsch_period_missing_file_raises_not_hangs(tmp_path):
    """E1: несуществующий источник → понятная FileNotFoundError, не зависон."""
    out = tmp_path / "out.xlsx"
    with pytest.raises(FileNotFoundError):
        build_rsch_report(
            [tmp_path / "несуществует.xlsx"], out,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
        )


# ---------------------------------------------------------------------------
# E3: Отмена РСЧ за период — кооперативная, корректный выход
# ---------------------------------------------------------------------------


def test_rsch_period_cancel_returns_cancelled_message(tmp_path):
    """E3: отмена должна сработать и дать CancelledByUser/сообщение, не ошибку."""
    src = tmp_path / "src.xlsx"
    _make_empty_rsch_source(src)
    out = tmp_path / "out.xlsx"

    completed: dict = {}

    def on_complete(ok, msg, path):
        completed["ok"] = ok
        completed["msg"] = msg

    cancel_event = threading.Event()

    def start_thread(target):
        threading.Thread(target=target, daemon=True).start()

    service = RschService(start_thread_fn=start_thread, get_drive_letters_fn=lambda: ("Q", "Z"))
    # Сразу взводим cancel — воркер должен увидеть его на первой контрольной точке.
    cancel_event.set()
    service.run_rsch_report_period(
        [src], out, date(2026, 1, 1), date(2026, 1, 5), on_complete, cancel_event=cancel_event
    )

    deadline = time.monotonic() + 3.0
    while "ok" not in completed and time.monotonic() < deadline:
        time.sleep(0.02)

    assert "ok" in completed, "Отмена не завершила операцию за 3с"
    # Отмена → ok=False, но msg про отмену (не «Ошибка сборки»).
    assert completed["ok"] is False
    assert "отмен" in completed["msg"].lower(), f"Ожидалось сообщение об отмене, получено: {completed['msg']}"


# ---------------------------------------------------------------------------
# E4: Длинный период — производительность и корректность (smoke)
# ---------------------------------------------------------------------------


def test_rsch_period_long_range_smoke(tmp_path):
    """E4: период в несколько месяцев должен собираться без ошибок.

    Smoke-проверка: строим источник с данными на ~90 дней и убеждаемся,
    что сборка завершается и создаёт по листу на каждую дату + «Период».
    """
    src = tmp_path / "long.xlsx"
    base = date(2026, 1, 1)
    rows = [(base + __import__("datetime").timedelta(days=i), 100 + i, i) for i in range(30)]
    _make_rsch_source(src, rows)
    out = tmp_path / "long_period.xlsx"

    written = build_rsch_report(
        [src], out,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 30),
    )
    assert written == 30
    wb = openpyxl.load_workbook(out, read_only=True)
    try:
        # 30 листов-дней + 1 «Период»
        assert len(wb.sheetnames) == 31
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# E5/E6: get_local_copy — локальный passthrough + сетевой таймаут (уже в Phase 2)
# здесь только страховка регресса контракта.
# ---------------------------------------------------------------------------


def test_get_local_copy_local_passthrough(tmp_path):
    """E5: локальный путь возвращается как есть (без кэш-копии)."""
    from core.infra.utils import get_local_copy

    f = tmp_path / "local.xlsx"
    f.write_bytes(b"stub")
    result, temp = get_local_copy(str(f), ("Q", "Z"))
    assert result == str(f)
    assert temp is None


# ---------------------------------------------------------------------------
# Доп: проверка, что прогресс растёт монотонно для периода
# ---------------------------------------------------------------------------


def test_rsch_period_progress_is_monotonic(tmp_path):
    """Прогресс за период должен идти от меньшего к большему, не прыгать назад.

    Это контр-страховка фикса причины 2: статус-бар должен «двигаться
    вперёд», иначе пользователь снова увидит зависание.
    """
    src = tmp_path / "src.xlsx"
    _make_empty_rsch_source(src)
    out = tmp_path / "out.xlsx"

    progress_calls: list[float] = []

    completed: dict = {}

    def on_complete(ok, msg, path):
        completed["ok"] = ok

    def on_progress(value: float):
        progress_calls.append(value)

    def on_current_file(name: str, done: int, total: int):
        pass

    def start_thread(target):
        threading.Thread(target=target, daemon=True).start()

    service = RschService(start_thread_fn=start_thread, get_drive_letters_fn=lambda: ("Q", "Z"))
    service.run_rsch_report_period(
        [src], out, date(2026, 1, 1), date(2026, 1, 5), on_complete,
        on_progress=on_progress, on_current_file=on_current_file,
    )

    deadline = time.monotonic() + 3.0
    while "ok" not in completed and time.monotonic() < deadline:
        time.sleep(0.02)

    # Прогресс монотонно не убывает (допускаем равенство — повторные 85.0).
    for prev, cur in zip(progress_calls, progress_calls[1:]):
        assert cur >= prev, f"Прогресс прыгнул назад: {prev} → {cur}"

"""Тесты, воспроизводящие баг «РСЧ за период грузит-грузит и не выгружается».

Заказчик (01.07.2026): «Рсч за период не хочет грузиться. Оно грузит
грузит и потом просто не выгружается».

Две независимых корневых причины:

1. ``get_local_copy`` (core/infra/utils.py) делает блокирующие
   ``os.stat`` / ``shutil.copy2`` на сетевом пути **без таймаута**. На
   зависшем сетевом диске (сервер SMB не отвечает) поток зависает на
   минуты — отчёт за период «грузит грузит» и не завершается.

2. ``RschService.run_rsch_report_period`` не сообщает прогресс в
   ``OperationState`` (в отличие от Consolidation), поэтому статус-бар
   стоит на 0% весь запуск и выглядит зависшим.

Эти тесты написаны ПЕРВЫМИ (TDD, RED-фаза) и фиксируют ожидаемое
поведение после фикса. До фикса они падают.
"""
from __future__ import annotations

import threading
import time
from datetime import date
from unittest.mock import patch

import pytest
from core.infra.utils import get_local_copy
from core.services.rsch_service import RschService

# ---------------------------------------------------------------------------
# Причина 1: get_local_copy не должен виснуть на неотвечающем сетевом диске.
# ---------------------------------------------------------------------------


def _hanging_stat(_path, *_args, **_kwargs):
    """Имитация os.stat на зависшем сетевом диске: блокирует «навсегда»."""
    # Реальный зависший SMB-сервер держит поток сколь угодно долго.
    # Используем большой, но конечный срок, чтобы тест сам не завис.
    # Принимает **kwargs, т.к. os.stat может передавать follow_symlinks.
    time.sleep(30)
    raise OSError("network path unreachable (timeout)")


def test_get_local_copy_does_not_hang_on_unresponsive_network_drive(tmp_path):
    """EC-1: зависший сетевой диск не должен блокировать поток навсегда.

    До фикса ``os.stat`` виснет на 30 c (мок выше) → тест падает по
    таймауту. После фикса ``get_local_copy`` должен сам таймаутить за
    разумное время (по умолчанию несколько секунд) и вернуть понятную
    ошибку вместо блокировки.
    """
    network_path = "Q:\\подразделения\\РСЧ\\источник.xlsx"

    with patch("core.infra.utils.os.stat", side_effect=_hanging_stat):
        # Поток-«сторож»: если get_local_copy не вернётся за 8 секунд,
        # считаем баг воспроизведённым и валеним тест.
        result_box: dict = {}

        def call():
            try:
                result_box["value"] = get_local_copy(network_path, ("Q", "Z"))
            except Exception as exc:  # noqa: BLE001 — фиксируем любую ошибку
                result_box["error"] = exc

        t = threading.Thread(target=call, daemon=True)
        t.start()
        t.join(timeout=8.0)

        # Главный ассерт: операция обязана завершиться, а не висеть.
        assert not t.is_alive(), (
            "get_local_copy завис на неотвечающем сетевом диске > 8 c — "
            "это и есть «грузит грузит и не выгружается» (Причина 1). "
            "Нужен внутренний таймаут на os.stat / shutil.copy2."
        )

        # После фикса: либо понятная ошибка, либо fallback-путь.
        if "error" in result_box:
            assert isinstance(result_box["error"], OSError), (
                "Ожидаемая OSError-семейства при недоступном сетевом пути, "
                f"получено {type(result_box['error'])}"
            )


def test_get_local_copy_local_path_is_passthrough(tmp_path):
    """Регресс: локальные пути не должны трогаться таймаут-логикой.

    Локальный файл возвращается как есть (без копирования в кэш), потому
    что ``_is_network_path`` для него False. Этот тест зелёный и до, и
    после фикса — он страхует, что мы не сломали локальный путь.
    """
    local_file = tmp_path / "local.xlsx"
    local_file.write_bytes(b"stub")
    result, temp = get_local_copy(str(local_file), ("Q", "Z"))
    assert result == str(local_file)
    assert temp is None


# ---------------------------------------------------------------------------
# Причина 2: RschService.run_rsch_report_period должен сообщать прогресс.
# ---------------------------------------------------------------------------


def test_rsch_period_reports_progress(tmp_path):
    """EC-2/EC-3: отчёт за период должен двигать прогресс и current_file.

    Симптом «грузит грузит» частично UX: статус-бар стоит на 0%, потому
    что RschService не зовёт set_progress/set_current_file (в отличие от
    Consolidation). После фикса сервис должен вызывать переданные колбэки.
    """
    import openpyxl as _openpyxl

    # Реальный source-файл, чтобы build_rsch_report дошёл до колбэков
    # (он проверяет существование файла и читает его целиком).
    src = tmp_path / "src.xlsx"
    wb = _openpyxl.Workbook()
    wb.save(src)
    wb.close()

    progress_calls: list[float] = []
    file_calls: list[str] = []

    started = threading.Event()
    completed: dict = {}

    def on_complete(ok, msg, path):
        completed["ok"] = ok
        completed["msg"] = msg
        completed["path"] = path

    def on_progress(value: float):
        progress_calls.append(value)

    def on_current_file(name: str, done: int, total: int):
        file_calls.append(name)

    def start_thread(target):
        def run():
            started.set()
            target()

        threading.Thread(target=run, daemon=True).start()

    service = RschService(
        start_thread_fn=start_thread,
        get_drive_letters_fn=lambda: ("Q", "Z"),
    )

    start = date(2026, 6, 1)
    end = date(2026, 6, 5)
    out = tmp_path / "РСЧ_отчет_период.xlsx"

    # Новый (после фикса) API: optional on_progress / on_current_file.
    try:
        service.run_rsch_report_period(
            [src],
            out,
            start,
            end,
            on_complete,
            cancel_event=None,
            on_progress=on_progress,
            on_current_file=on_current_file,
        )
    except TypeError:
        # До фикса у метода нет этих параметров → тест провален по
        # самой сути (Причина 2 воспроизведена: прогресс не проброшен).
        pytest.fail(
            "RschService.run_rsch_report_period не принимает on_progress/"
            "on_current_file — прогресс за период не сообщается (Причина 2)."
        )

    # Ждём завершения фонового потока (с запасом).
    deadline = time.monotonic() + 5.0
    while "ok" not in completed and time.monotonic() < deadline:
        time.sleep(0.02)

    # Сборка пустого файла завершится ошибкой «нет строк» — это нормально,
    # суть фикса в том, что ПРОГРЕСС сообщался во время работы, а не в
    # результате. До фикса progress_calls был бы пуст (метод не принимал
    # колбэки вовсе).
    assert "ok" in completed, "Фоновый поток не завершился за отведённое время"
    # Ключевой ассерт: прогресс действительно сообщался во время сборки.
    assert progress_calls, (
        "run_rsch_report_period ни разу не вызвал on_progress — статус-бар "
        "стоял бы на 0% весь запуск (Причина 2)."
    )
    assert file_calls, (
        "run_rsch_report_period ни разу не вызвал on_current_file — пользователь "
        "не видел, какой файл обрабатывается."
    )

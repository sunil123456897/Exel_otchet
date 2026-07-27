# Спецификация фикса: «РСЧ за период» грузит-грузит и не выгружается

## Симптом (от заказчика, 01.07.2026)
> «Рсч за период не хочет грузиться. Оно грузит грузит и потом просто не выгружается»

## Phase 0 — Анализ корневой причины

Путь фичи: `gui_master.run_rsch_report_month` → `RschCommandsMixin.run_rsch_report_month`
→ `AppController.run_rsch_report_period` → `RschService.run_rsch_report_period`
→ `build_rsch_report` (period branch) → `_collect_rows_from_workbook`
→ `get_local_copy`.

### 🔴 Причина 1 — блокирующее сетевое чтение без таймаута (РЕАЛЬНЫЙ зависон)
`APP/core/infra/utils.py:180` `get_local_copy` вызывает `os.stat(network_path)`
и `shutil.copy2(network_path, local_path)` **без таймаута**. На зависшем
сетевом диске (сервер SMB не отвечает, сессия не разорвана) обе операции
блокируют поток на десятки секунд / минуты. Для отчёта за период это
умножается на число исходных файлов → видимый бесконечный «грузит».

Проект уже содержит правильный паттерн `path_exists_with_timeout`
(`utils.py:245`, ThreadPoolExecutor + timeout), но для копирования он не
применяется.

### 🟠 Причина 2 — отсутствие прогресса для RSCH (UX-зависон)
`OperationState.set_progress` / `set_current_file` вызываются **только** из
`ConsolidationViewModel` (`gui_master.py:98-102, 256-272`). `RschService`
(`rsch_service.py`) **ни разу** их не вызывает → во время «Сборки РСЧ за
период» статус-бар стоит на 0% весь запуск → выглядит зависшим.

## Phase 1 — Edge-cases (спецификация)
- **EC-1**: `get_local_copy` на сетевом пути с неотвечающим сервером должна
  завершаться за ограниченное время (return или понятный `IOError`), а не
  блокировать поток навсегда.
- **EC-2**: `RschService.run_rsch_report_period` должна принимать и вызывать
  `on_progress` / `on_current_file`, чтобы статус-бар двигался.
- **EC-3**: Прогресс должен расти по мере обработки каждого источника и каждой
  даты в периоде.
- **EC-4**: Отмена (`cancel_event`) должна срабатывать даже во время ожидания
  сетевого диска (кооперативная).

## Phase 2 — Критерии приёмки (тесты)
- `tests/test_rsch_period_hang.py::test_get_local_copy_does_not_hang_on_unresponsive_network_drive`
- `tests/test_rsch_period_hang.py::test_rsch_period_reports_progress`

## Phase 3 — План фикса
1. `get_local_copy`: обернуть `os.stat` и `shutil.copy2` в ThreadPoolExecutor
   с timeout (параметризуемый, по умолчанию ~5 c); при таймауте — `IOError`
   с понятным сообщением. Уважает `cancel_event` где возможно.
2. `RschService.run_rsch_report_period` (+`run_rsch_report`): добавить optional
   `on_progress`/`on_current_file`, пробросить в `build_rsch_report`.
3. `build_rsch_report`: принимать и вызывать колбэки per-source / per-date.
4. `RschCommandsMixin.run_rsch_report_month`: передать колбэки из `operation_state`.

Обратная совместимость: все новые параметры optional.

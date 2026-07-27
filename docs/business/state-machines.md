# Диаграммы состояний

## Метаданные
- Дата: 2026-06-26
- Проект: Master-Report v5.5
- Источник: docs/features/inventory.md + анализ кода APP/core/

---

## SM-001: Consolidation Session
- Сущность: Session (консолидация дневная/все даты/период)
- Состояния: running, completed, completed_with_warnings, failed, cancelled
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | (создание) | running | _execute_consolidation start, save_session | UUID генерируется, session_id в БД |
  | running | failed | date_error / no_files / empty_data / write_error / exception | on_failure_code, on_complete(False, msg, None) |
  | running | cancelled | cancel_event.is_set() после engine/consolidate | _cancel_message, mark_partial |
  | running | completed | write_report success, no actionable/runtime warnings | on_complete(True, msg, path) |
  | running | completed_with_warnings | write_report success, has actionable OR runtime warnings | on_complete(True, msg, path) |
- Начальное состояние: running
- Конечные состояния: completed, completed_with_warnings, failed, cancelled

## SM-002: Employee Refresh Status
- Сущность: Employee status для выбранной даты
- Состояния: 🟢 ГОТОВО, 🟠 НЕТ ДАТЫ, 🔴 НЕТ ФАЙЛА, [ERR] ОШИБКА, (не проверено)
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | (не проверено) | 🔴 НЕТ ФАЙЛА | файл не существует по привязанному пути | — |
  | (не проверено) | [ERR] ОШИБКА | ошибка при чтении файла | error_message в результат |
  | (не проверено) | 🟠 НЕТ ДАТЫ | файл существует, лист за дату не найден ИЛИ target_date > today | — |
  | (не проверено) | 🟢 ГОТОВО | файл существует + лист за дату найден | — |
  | любой | (не проверено) | изменение даты / add/delete_employee / attach_files | discovery_cache инвалидация |
- Начальное состояние: (не проверено)
- Конечные состояния: 🟢 ГОТОВО, 🟠 НЕТ ДАТЫ, 🔴 НЕТ ФАЙЛА, [ERR] ОШИБКА

## SM-003: OperationState (UI)
- Сущность: Глобальная операция (refresh/consolidation/rsch/reconciliation)
- Состояния: idle, busy, cancelling
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | idle | busy | begin() — is_busy=False | listeners уведомлены, progress bar показан |
  | busy | busy | begin() — is_busy=True | отказ (double-click protection) |
  | busy | cancelling | request_cancel() — is_busy=True | cancel_event.set() |
  | busy | idle | end() | listeners уведомлены, progress bar скрыт |
  | cancelling | idle | end() (после cancel processed) | _cancel_message, mark_partial |
- Начальное состояние: idle
- Конечные состояния: idle

## SM-004: Auto-Reconciliation Flow
- Сущность: Автосверка (run_auto_reconciliation_day)
- Состояния: started, master_reports_built, rsch_built, reconciliation_built, completed, skipped, failed
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | started | master_reports_built | _run_auto_master_report для всех кураторов success | 3 мастер-отчёта готовы |
  | started | failed | _run_auto_master_report для общего raise RuntimeError | error message |
  | started | completed | _run_auto_master_report для куратора ConsolidationRunError empty_data → write_empty_daily_report | пустые отчёты кураторов |
  | master_reports_built | rsch_built | build_rsch_report success | РСЧ-отчёт готов |
  | master_reports_built | skipped | РСЧ rows == 0 | «Нет данных РСЧ. Автосверка пропущена.» |
  | master_reports_built | failed | cancel_event после master reports | _cancel_message |
  | rsch_built | reconciliation_built | build_combined_reconciliation_report success | отчёт сверки готов |
  | rsch_built | completed | build_combined raises ValueError | «Сверка за дату: {error}» |
  | rsch_built | failed | cancel_event после РСЧ | _cancel_message |
  | reconciliation_built | completed | success | «Автосверка собрана: ...» |
- Начальное состояние: started
- Конечные состояния: completed, skipped, failed

## SM-005: Settings Dialog
- Сущность: Settings dialog (deep copy config)
- Состояния: closed, open_clean, open_dirty, applying, cancelled
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | closed | open_clean | open settings dialog | deep copy config, snapshot темы |
  | open_clean | open_dirty | изменение любого поля | live preview темы/масштаба |
  | open_dirty | open_clean | undo/revert | восстановление snapshot |
  | open_dirty | applying | Apply/OK | save_config, для OK — close dialog |
  | open_dirty | cancelled | Cancel | восстановление snapshot, close dialog |
  | applying | open_clean | Apply (не OK) | save_config, dialog остаётся |
  | applying | closed | OK | save_config, close dialog |
  | cancelled | closed | — | close dialog |
- Начальное состояние: closed
- Конечные состояния: closed

## SM-006: Theme
- Сущность: Активная тема приложения
- Состояния: light, dark, system_resolved, system_polling
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | (старт) | light | config ui.theme=light | apply light palette |
  | (старт) | dark | config ui.theme=dark | apply dark palette |
  | (старт) | system_resolved | config ui.theme=system | detect OS theme |
  | system_resolved | system_polling | startup complete | polling каждые 5s |
  | system_polling | light | OS theme changed to light | re-apply palette |
  | system_polling | dark | OS theme changed to dark | re-apply palette |
  | любой | light | user settings change to light | stop polling, apply light |
  | любой | dark | user settings change to dark | stop polling, apply dark |
  | любой | system_resolved | user settings change to system | detect + start polling |
- Начальное состояние: (из config)
- Конечные состояния: light, dark (system — polling, не terminal)

## SM-007: File Cache (discovery/file_cache)
- Сущность: Cache entry для файла
- Состояния: absent, valid, stale
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | absent | valid | get_file_cache miss → read file → save cache | mtime+size записаны |
  | valid | stale | file mtime/size changed | cache miss при следующем чтении |
  | stale | valid | re-read file → save cache | обновлённые mtime+size |
  | valid | absent | add/delete_employee / attach_files | инвалидация |
- Начальное состояние: absent
- Конечные состояния: valid (при активном использовании)

## SM-008: Excel Backup Rotation
- Сущность: Backup files в backups/excel_outputs/{stem}/
- Состояния: active (один из N последних), pruned (удалён)
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | (нет backup) | active | backup_existing_excel_output | copy2, timestamp в имени |
  | active | active | новый backup (остаётся в N последних) | — |
  | active | pruned | count > keep (N) | unlink старейшего по mtime |
- Начальное состояние: (нет backup)
- Конечные состояния: active (в rotation), pruned (удалён)

## SM-009: RSCH Sources Selection
- Сущность: Выбор исходных файлов РСЧ
- Состояния: none_selected, saved_available, saved_missing, user_selecting, resolved
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | none_selected | saved_available | recent_sources exist | askyesnocancel «Использовать сохраненный?» |
  | none_selected | user_selecting | no recent_sources ИЛИ user click «Нет» | multi-file dialog |
  | saved_available | resolved | user click «Да» | use saved sources |
  | saved_available | user_selecting | user click «Нет» | multi-file dialog |
  | saved_available | saved_missing | some saved paths not exist | warning «Сохраненные пути не найдены» |
  | saved_missing | resolved | filter existing saved paths | use existing subset |
  | user_selecting | resolved | user selects files | save recent_sources, last_output_dir |
  | user_selecting | none_selected | user cancels dialog | отмена операции |
- Начальное состояние: none_selected
- Конечные состояния: resolved, none_selected (cancel)

## SM-010: Reconciliation Target Date Resolution
- Сущность: Target date для сверки
- Состояния: explicit, auto_single, auto_none, auto_multiple, resolved, error
- Переходы:
  | Из | В | Условие | Побочный эффект |
  | (старт) | explicit | target_date передан | проверка наличия листа в обоих файлах |
  | explicit | resolved | листы найдены в обоих файлах | — |
  | explicit | error | лист не найден в одном из файлов | ValueError |
  | (старт) | auto_single | 1 common date | — |
  | auto_single | resolved | — | — |
  | (старт) | auto_none | 0 common dates | — |
  | auto_none | error | — | ValueError «Не найдена общая дата» |
  | (старт) | auto_multiple | >1 common dates | — |
  | auto_multiple | error | — | ValueError «Выберите нужную дату» |
- Начальное состояние: (старт)
- Конечные состояния: resolved, error

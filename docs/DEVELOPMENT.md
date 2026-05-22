# Development Guide

Правила безопасной разработки проекта Master-Report.

## Принцип

Сначала сохранить рабочее поведение, потом улучшать. Проект работает с реальными финансовыми Excel-файлами, поэтому любые изменения в чтении, расчетах, форматах и путях должны быть маленькими и проверяемыми.

## Перед Изменениями

1. Понять пользовательский сценарий.
2. Найти минимальное место изменения.
3. Посмотреть существующие тесты рядом с этим поведением.
4. Для функций/классов запустить GitNexus impact-анализ.
5. Если риск высокий, сначала зафиксировать причину и план проверки.

## Архитектурные Границы

```text
UI -> ViewModels / GuiCommands -> AppController -> Domain / Infra
```

Правила:

- UI не должен содержать финансовую бизнес-логику.
- `AppController` координирует, но не должен становиться местом расчетов.
- `LogicService` отвечает за бизнес-правила.
- `infra` отвечает за файлы, Excel, SQLite, сеть и форматирование.
- Конфигурация должна оставаться переносимой между ПК.
- Runtime validation boundary для финансовых строк сейчас находится в `Validator` и `LogicService`; `FinancialRowSchema` не является строгим барьером рабочего ingestion-потока.

Sentrux/GitNexus baseline фиксировать только по свежему запуску инструментов в текущей сессии. Если Sentrux отвечает `No scan data` или scan-инструмент недоступен, не записывать это как зеленый архитектурный gate.

## Команды Проверки

Быстрый targeted-loop:

```bash
pytest tests/test_нужный_файл.py
python -m ruff check APP tests
python -m mypy APP tests
```

Полный gate:

```bash
pytest tests
python -m ruff check APP tests
python -m mypy APP tests
python -m compileall -q APP
```

GitHub Actions запускает тот же gate на `windows-latest` при `push` в `main` и при pull request:

```text
.github/workflows/quality-gate.yml
```

CI ставит зависимости с нуля из `requirements-dev.txt`, выполняет `python -m pip check` и не использует dependency cache, чтобы устаревший кэш не скрывал проблемы чистой установки.

Для широких изменений Excel-логики дополнительно проверять итоговую книгу через `openpyxl`:

- имена листов;
- заголовки;
- количество строк;
- отсутствие повторных заголовков внутри данных;
- отсутствие `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`;
- ожидаемые числовые форматы;
- ожидаемые warning-цвета.

## Как Выбирать Тесты

| Зона | Тесты |
| --- | --- |
| Controller | `tests/test_app_controller.py`, `tests/test_app_controller_extended.py` |
| Bootstrap/config | `tests/test_bootstrap.py`, `tests/test_bootstrap_extended.py`, `tests/test_config_controller.py` |
| Excel parsing | `tests/test_ingestion_core.py`, `tests/test_ingestion_engine*.py` |
| Discovery/network paths | `tests/test_discovery_service.py`, `tests/test_discovery_service_extended.py`, `tests/test_discovery_service_properties.py` |
| Business rules | `tests/test_logic_service.py`, `tests/test_logic_service_extended.py`, `tests/test_logic_service_property.py` |
| Excel output | `tests/test_export_writer.py`, `tests/test_export_writer_extended.py`, `tests/test_export_styles.py` |
| Curators | `tests/test_curators.py`, relevant controller tests |
| RSCH | `tests/test_rsch_report.py`, `tests/test_rsch_report_edge_cases.py`, `tests/test_rsch_report_formatting.py`, `tests/test_gui_commands_rsch.py` |
| GUI | `tests/test_gui.py`, `tests/test_gui_components.py` |

## Правила Для Excel

- Не читать и затем сохранять книгу с `data_only=True`.
- Не менять названия колонок без тестов на writer и downstream consumers.
- Не удалять warning-логику без проверки реальных файлов.
- Не считать все желтые/красные ячейки ошибкой: часть предупреждений ожидаема.
- В РСЧ нулевая строка с бизнес-текстом должна попадать в отчет как warning, но строка без бизнес-текста и только со счетом считается пустой и пропускается.
- Для процентов использовать формат без лишней запятой у целых процентов и с дробной частью только когда она реально есть.
- Для больших денежных/транзитных чисел использовать читаемый числовой формат.

## Правила Для Дат

- Для обычных отчетов листы без года не валидны.
- Для диапазона дат брать только листы внутри диапазона.
- Для куратора дата идет через имя листа.
- Для РСЧ допустимы листы, где нормализованное имя содержит `рсч`, кроме шаблонов.

## Правила Для Производительности

- Не включать полный сетевой scan на обычный старт.
- Сетевые корни сканировать только при реальной необходимости.
- Не читать неизмененные файлы повторно без причины.
- Предпочитать кэш/сохраненную карту сотрудников для статуса.
- Любую оптимизацию проверять логом времени или focused performance/regression test.

## Правила Для Конфигов

- Не коммитить machine-specific пути как обязательные значения.
- Портируемые пути должны быть относительными, где это возможно.
- Для рабочего ПК с сетевым диском использовать `Q:\...`, а не путь с личного диска разработчика.
- `database.allow_local_fallback` по умолчанию не должен скрывать production-ошибки путей.
- Отсутствующий файл сотрудника при сборке должен попадать в список ошибок обработки файлов, а не превращаться в тихие `0` строк.

## Git Safety

- Не делать destructive git-команды.
- Не откатывать чужие изменения.
- Перед финалом смотреть `git status`.
- Перед commit/stage проверять scope через GitNexus detect changes.

## Repo Data Hygiene

- Рабочие папки с реальными входными файлами (`REPORTS/`, массовые РСЧ-источники и временные результаты сверки) не добавлять в Git без отдельного явного решения.
- Трекать можно только необходимые шаблоны, согласованные рабочие baseline-выходы и небольшие regression fixtures под `tests/fixtures/` или `tests/golden/`.
- Новые regression Excel-файлы должны быть минимальными и обезличенными. Если нужен реальный кейс из рабочего отчета, сначала воспроизвести его в маленьком fixture, а оригинал оставить вне Git.
- Не удалять уже существующие реальные Excel-файлы из рабочей папки в рамках “уборки” без отдельного подтверждения пользователя.

## AI Agent Workflow

Минимальный рабочий цикл:

1. Прочитать `README.md` и `docs/AI_CONTEXT.md`.
2. Найти точку изменения по карте кода.
3. Сделать impact-анализ для изменяемого символа.
4. Написать/обновить focused test, если меняется поведение.
5. Сделать маленькую правку.
6. Запустить focused tests.
7. Запустить ruff/mypy для затронутой зоны или всего проекта.
8. Запустить полный gate, если изменение широкое.
9. Коротко отчитаться: файлы, что изменено, проверки, риски.

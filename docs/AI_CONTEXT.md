# AI Context Map

Этот файл нужен для быстрого входа в проект человеком или ИИ-агентом. Он намеренно короткий и указывает, куда смотреть дальше.

## Суть Проекта

Master-Report - Windows-first приложение для финансовой консолидации Excel-отчетов. Оно читает много файлов сотрудников, нормализует строки, применяет бизнес-правила и записывает итоговые Excel-файлы.

Основные выходы:

- общий `Master_Report.xlsx`;
- `APP/output/boris_report.xlsx`;
- `APP/output/ivan_report.xlsx`;
- общий РСЧ-файл в папке `РСЧ`.
- отдельный отчет расхождений между готовым мастер-отчетом и готовым РСЧ.

## Минимальная Карта Кода

```text
APP/main.py
  запускает GUI

APP/core/bootstrap.py
  читает config.yaml, собирает контроллеры, БД, reader, writer, services

APP/core/app_controller.py
  оркестрирует действия UI: статусы, сборки, РСЧ, shutdown

APP/core/domain/logic_service.py
  бизнес-правила финансовых строк и кураторских отчетов

APP/core/infra/ingestion_reader.py
  читает Excel, ищет листы и заголовки

APP/core/infra/ingestion_engine.py
  запускает чтение файлов и готовит данные для обработки

APP/core/infra/discovery_service.py
  ищет/обновляет пути к файлам сотрудников

APP/core/infra/export_writer.py
  пишет общий и кураторские Excel-отчеты

APP/core/infra/export_formatting.py
  формат чисел, процентов, ширин и стилей в Excel

APP/core/infra/rsch_report.py
  собирает РСЧ-отчет

APP/core/infra/reconciliation_report.py
  сверяет готовый мастер-отчет с готовым РСЧ и пишет отчет расхождений

APP/core/ui/
  Tkinter GUI: окно, боковая панель, таблица статусов, команды

tests/
  регрессии, unit/integration/GUI/Excel tests
```

## Главные Потоки

### Запуск

```text
APP/main.py
  -> Bootstrap.setup(...)
  -> AppController(...)
  -> GuiMaster(...)
  -> GuiCommands / ViewModels
```

### Сборка Обычного Отчета

```text
UI
  -> ConsolidationViewModel
  -> AppController.run_consolidation(...)
  -> file_processor.process_file_task(...)
  -> IngestionEngine / CalamineReader
  -> LogicService
  -> MasterWriter
```

### Статусы Сотрудников

```text
UI refresh
  -> AppController.refresh_status(...)
  -> DiscoveryService.get_employees_map(allow_network_scan=False)
  -> быстрый статус по сохраненным путям без полного сетевого скана
```

Полный сетевой поиск нужен только когда требуется переобнаружить файлы.

### РСЧ

```text
UI
  -> GuiCommands.run_rsch_report(...)
  -> AppController.run_rsch_report(...)
  -> RschReportBuilder
  -> один общий файл
```

Режим отдельных РСЧ-файлов убран из GUI.

### Сверка Мастер-Отчета С РСЧ

```text
UI
  -> GuiCommands.run_reconciliation_report(...)
  -> build_reconciliation_report(master, rsch, output, target_date)
  -> отдельный Excel с колонками куратора, статусом и колонками РСЧ
```

Сверка читает уже готовые файлы и не изменяет исходный мастер-отчет или РСЧ.

## Что Нельзя Ломать

- Не менять публичные сценарии GUI без явной причины.
- Не отбрасывать Ивановские transit/FX строки из-за нулевых сумм.
- Не трактовать `DD.MM` как дату текущего года для обычной консолидации.
- Не сохранять книги после чтения с `data_only=True`.
- Не убирать предупреждения в реальных Excel-данных без проверки бизнес-смысла.
- Не включать полный сетевой скан в стартовый refresh, иначе запуск снова станет медленным.
- Не удалять Excel-файлы и реальные отчеты при уборке мусора.

## Частые Точки Изменений

| Нужно изменить | Смотреть сначала |
| --- | --- |
| Колонки и бизнес-расчеты | `APP/core/domain/logic_service.py`, tests `test_logic_service*` |
| Чтение Excel | `APP/core/infra/ingestion_reader.py`, `ingestion_engine.py` |
| Формат Excel | `APP/core/infra/export_writer.py`, `export_formatting.py` |
| Пути и переносимость | `APP/core/bootstrap.py`, `path_resolver.py`, `config_controller.py` |
| Быстродействие загрузки | `discovery_service.py`, `app_controller.py` |
| GUI размер/панель | `gui_master.py`, `ui_sidebar.py` |
| РСЧ | `rsch_report.py`, `rsch_report_formatting.py`, `gui_commands.py` |
| Сверка с РСЧ | `reconciliation_report.py`, `gui_commands.py` |

## Проверки По Типам Изменений

| Изменение | Минимальные проверки |
| --- | --- |
| GUI | `pytest tests/test_gui.py tests/test_gui_components.py` |
| РСЧ | `pytest tests/test_rsch_report.py tests/test_rsch_report_edge_cases.py tests/test_gui_commands_rsch.py` |
| Сверка с РСЧ | `pytest tests/test_reconciliation_report.py tests/test_gui_commands_rsch.py` |
| Excel writer/formatting | `pytest tests/test_export_writer.py tests/test_export_writer_extended.py tests/test_export_styles.py` |
| Ingestion | `pytest tests/test_ingestion_engine*.py tests/test_ingestion_core.py` |
| Controller | `pytest tests/test_app_controller.py tests/test_app_controller_extended.py` |
| Config/bootstrap | `pytest tests/test_bootstrap.py tests/test_bootstrap_extended.py tests/test_config_controller.py` |

Перед финалом для широких изменений:

```bash
pytest tests
python -m ruff check APP tests
python -m mypy APP tests
```

## Документы

- `README.md` - входная страница.
- `docs/PROJECT_AI_GUIDE.md` - полный рабочий гид.
- `docs/OPERATIONS.md` - эксплуатация на рабочем ПК.
- `docs/DEVELOPMENT.md` - правила разработки и проверок.
- `docs/knowledge_base/ARCHITECTURE.md` - архитектура.
- `docs/knowledge_base/INGESTION_PIPELINE.md` - чтение Excel.
- `docs/knowledge_base/FINANCIAL_LOGIC.md` - финансовая логика.
- `docs/knowledge_base/NETWORK_OPTIMIZATION.md` - сеть и производительность.

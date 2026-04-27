# Master Report Consolidator v6.0

Система автоматизации финансовых отчетов для консолидации данных из сотен Excel-файлов сотрудников в единый мастер-отчет.

## Ключевые особенности (v6.0)
*   **Гибридная схема (SQL + Excel)**: Использует SQLite в качестве вычислительного ядра для молниеносной агрегации данных, сохраняя Excel как удобный интерфейс.
*   **Умное отслеживание (Smart Tracking)**: Детекция изменений файлов по `inode` и `MD5` хэшам (не перечитывает файлы, которые не менялись).
*   **Сетевая устойчивость**: Встроенные механизмы повторных попыток (Retries) и WAL-режим БД для стабильной работы на общих сетевых дисках.
*   **Финансовая точность**: Все расчеты выполняются через тип `Decimal` с нулевой погрешностью округления.

## Требования
*   Python 3.12+
*   Зависимости: `openpyxl`, `pyxlsb`, `pyyaml`, `tkcalendar`. Установка: `pip install -r requirements.txt`.

## Настройка (`APP/config.yaml`)
В новой версии добавлены секции для управления базой данных и блокировками:

```yaml
# Настройка базы данных кэша
database:
  path: "APP/cache.db"
  use_wal: true      # Включить режим WAL для работы в сети
  timeout: 30.0      # Таймаут ожидания разблокировки БД

# Настройка сетевых блокировок
locking:
  retry_count: 5     # Количество попыток при блокировке файла
  retry_backoff: 2.0 # Пауза между попытками (сек)
```

## Как запустить
*   **Windows**: запустите `ЗАПУСК.bat`.
*   **Python напрямую**:

```bash
python -m pip install -r requirements.txt
python APP/main.py
```

## Проверка качества

Для разработки установите dev-зависимости:

```bash
python -m pip install -r requirements-dev.txt
```

Полный gate перед завершением работы:

```bash
pytest tests
python -m ruff check APP tests
python -m mypy APP tests
pytest --cov=APP/core --cov-report=term-missing tests
```

Текущий ожидаемый baseline: все тесты проходят, Ruff проходит, mypy проходит, coverage выше 90%.

Подробная документация для людей и ИИ-агентов: [docs/PROJECT_AI_GUIDE.md](docs/PROJECT_AI_GUIDE.md).

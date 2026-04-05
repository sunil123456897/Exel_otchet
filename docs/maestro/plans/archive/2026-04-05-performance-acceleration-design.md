---
design_depth: deep
task_complexity: complex
date: 2026-04-05
topic_slug: performance-acceleration
---

# Design Document: Master-Report v5.5 "Elite" - Performance Acceleration

## 1. Problem Statement
Текущая версия 5.5 "Elite" достигла высоких показателей (150k строк за 3.72с), однако аудит выявил потенциальные боттлнеки при масштабировании на 500k+ строк и 24+ параллельных источника. Основными проблемами являются использование медленного `re.sub` в горячих циклах, накладные расходы Pydantic валидации, конкуренция при записи в SQLite и последовательная обработка файлов в контроллере.

## 2. Requirements

### Functional
- REQ-F1: Оптимизация `to_decimal` для ускорения очистки строк без потери точности — *критично для горячих циклов*.
- REQ-F2: Перенос `ThreadPoolExecutor` на уровень обработки файлов в `_run_engine` — *устраняет последовательное ожидание IO*.
- REQ-F3: Реализация Producer-Consumer очереди для записи в БД — *гарантирует отсутствие конфликтов SQLite*.

### Non-Functional
- REQ-NF1: Снижение времени парсинга 150k строк до < 2 секунд на стандартном железе.
- REQ-NF2: Сохранение 100% точности Decimal-расчетов.
- REQ-NF3: Пиковое потребление RAM не должно превышать 1GB при обработке 500k строк.

### Constraints
- C1: Pure Python implementation — *запрет на использование Cython/Rust*.
- C2: Сохранение существующих Pydantic схем как основы структуры данных.

## 3. Approach

### Selected Approach: "Streamlined Elite" (Producer-Consumer & Hot-Loop Tuning)
Данный подход фокусируется на устранении архитектурных трений при сохранении надежности.

- **Producer-Consumer (DB)** — Использование одного выделенного потока для записи через queue.Queue. Traces To: REQ-F3.
- **Optimized Pydantic (model_construct)** — Обход дорогой валидации в циклах парсинга. Traces To: REQ-NF1.
- **Fast String Processing** — Замена regex на `str.translate` или `str.replace`. Traces To: REQ-F1.

### Decision Matrix (Deep Mode)
| Criterion | Weight | Elite Approach | Raw Dicts |
|-----------|--------|----------------|-----------|
| Speed | 40% | 5: Parallel + Queue | 4: Raw speed |
| Accuracy | 30% | 5: Strong typing | 3: Type loss |
| Stability | 20% | 5: Single Writer | 4: WAL risk |
| Maintainability | 10% | 4: Standard patterns | 5: Simpler code |
| **Weighted Total** | | **4.9** | **3.9** |

## 4. Architecture

### Data Flow
1. **AppController** инициализирует `queue.Queue` и запускает фоновый поток **DBWriterThread**.
2. **ThreadPoolExecutor** запускает N потоков **FileProcessor**.
3. **FileProcessor** читает файл через Calamine, применяет оптимизированный `to_decimal`, создает объекты через `model_construct()` и кладет результат в очередь.
4. **DBWriterThread** вычитывает очередь батчами и выполняет `executemany` в SQLite.

### Rationale
- Использование очереди изолирует "шумный" диск от "быстрых" вычислений. Traces To: REQ-F3.
- Батчевая запись снижает количество COMMIT-ов в SQLite. Traces To: REQ-NF1.

## 5. Agent Team
- `performance_engineer` — Разработка оптимизированного `to_decimal` и настройка SQLite PRAGMA. Traces To: REQ-NF1.
- `coder` — Реализация Producer-Consumer в AppController. Traces To: REQ-F2, REQ-F3.
- `code_reviewer` — Аудит потокобезопасности.
- `tester` — Создание бенчмарка производительности. Traces To: REQ-NF1, REQ-NF2.

## 6. Risk Assessment
- **Risk 1: Memory Bloat** — Mitigation: Использование bounded queue (maxsize=10000). Traces To: REQ-NF3.
- **Risk 2: Silent Data Loss** — Mitigation: Реализация Graceful Shutdown. Traces To: REQ-F3.
- **Risk 3: SQLite Durability** — Mitigation: Сохранение метаданных о статусе файлов.

## 7. Success Criteria
1. Время парсинга 150,000 строк снижено до < 2 секунд.
2. Система выдерживает 32+ параллельных источника без блокировок БД.
3. Точность Decimal подтверждена тестами.
4. Устранение regex из горячих циклов.

---
title: "Automated Destructive Test Harness Simulation"
date: "2026-03-29"
design_depth: "deep"
task_complexity: "complex"
---

# Destructive Tester Design: v5.5 (Headless Simulation)

## 1. Problem Statement & Scope
Текущие "Миссии ручного тестирования" (1-4) требуют имитации сложных состояний (File Lock, Race Conditions, DB Corruption), которые невозможно выполнить в терминале ИИ через стандартный GUI.
**Цель:** Создать `destructive_tester_v5_5.py` — автономный симулятор, который программно реализует все 4 миссии, используя прямой импорт классов приложения и Monkey-patching для "инъекции" сбоев в критические точки кода.

## 2. Architecture & Components
Симулятор строится как модульный оркестратор, не зависящий от Tkinter.

### 2.1. Environment Manager (`HarnessEnv`)
- Создает временную рабочую область `temp_destructive_env/`.
- Инициализирует чистый `config.yaml` и `cache.db`.
- *Rationale:* Изоляция тестов гарантирует отсутствие влияния "мусора" (Dirty State) от предыдущих прогонов.

### 2.2. Poison Data Generator (`EvilGenerator`)
- Генерирует "ядовитые" Excel-файлы (.xlsx/.xlsb) для Миссий 3 и 4.
- Кейсы: двойные шапки, листы "32.01", скрытые листы, миллиардные суммы, битые форматы чисел.
- *Rationale:* Использование `openpyxl` и `pyxlsb` напрямую для программного создания дефектов.

### 2.3. Fault Injection Engine (`MonkeySaboteur`)
- Перехватывает вызовы методов через `setattr` в памяти.
- **Точки инъекции (Targets):**
    - `SQLiteManager._execute_with_retry`: Внедрение искусственных `sqlite3.OperationalError("database is locked")` для Миссии 1.
    - `IngestionEngine._read_xlsx`: Внедрение `time.sleep(n)` внутри цикла чтения строк для имитации "подвисания" диска (Миссия 1 & 2).
    - `os.replace` (вызываемый в `MasterWriter._save_workbook`): Подмена на `PermissionError` для имитации открытого в Excel файла (Миссия 1).
- *Considered Alt:* `unittest.mock` — Отклонено, так как моки часто ведут себя слишком предсказуемо и не позволяют проверить реальное состояние файлов на диске.

### 2.4. Mission Orchestrator (`MissionRunner`)
- Запускает сценарии Миссий 1-4.
- Использует `threading.Thread` для имитации "спама кнопками" (Миссия 2) и `multiprocessing.Process` для имитации "Kill Process" (Миссия 2), чтобы не убить сам процесс оркестратора.

## 3. Mission Mapping (Traceability)
| Миссия | Архитектурная цель | Механизм симуляции |
|---|---|---|
| **1. File Juggler** | I/O Integrity | `os.replace` -> `PermissionError` + удаление `config.yaml` mid-flight |
| **2. Chaotic Clicker** | Race Conditions | Parallel `threading.Thread` calls + `os._exit(1)` in child process |
| **3. Evil Accountant** | Ingestion Engine | `EvilGenerator` creating files with malformed headers/sheet names |
| **4. Extreme Math** | Business Logic | Data sets with 0/100% commissions and $10B+ values |

## 4. Validation (Success Criteria)
**Правило "Hard Stop":**
1. **No Silent Data Loss:** Итоговый отчет либо точен, либо его генерация безопасно прервана.
2. **No Phantom Threads:** Все потоки завершаются корректно даже после сбоя.
3. **Graceful Error Handling:** Все ошибки логируются в `AppController` без выброса необработанных исключений в консоль.

---
**Approver:** Maestro Orchestrator  **Depth:** Deep

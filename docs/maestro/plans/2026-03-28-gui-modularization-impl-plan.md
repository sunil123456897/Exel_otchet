---
title: "План реализации: Декомпозиция GUI"
date: 2026-03-28
status: pending_approval
task_complexity: medium
---

# План реализации рефакторинга GUI

## 1. Обзор плана
Этот план описывает перенос кода из `gui_master.py` в модульную структуру (Components + Controllers). Цель — повышение модульности и упрощение поддержки.

## 2. Граф зависимостей
```
Phase 1 (Foundation)
    |
Phase 2 (UI Extraction)
    |
Phase 3 (Logic Extraction)
    |
Phase 4 (Integration)
```

## 3. Таблица стратегии выполнения
| Фаза | Агент | Модель | Блокировки | Описание |
|------|-------|--------|------------|----------|
| 1 | Architect | Pro | - | theme.py и utils/helpers.py. |
| 2 | Coder | Pro | 1 | Создание классов в components/. |
| 3 | Refactor | Pro | 2 | Создание контроллеров, вынос логики. |
| 4 | Coder | Flash | 3 | Финальная сборка и тесты. |

## 4. Детали фаз

### Фаза 1: Foundation (Architect)
- **Цель**: Выделить общие ресурсы.
- **Файлы для создания**: `APP/src/theme.py`, `APP/src/utils/helpers.py`.
- **Валидация**: Импорт стилей в тестовом скрипте.

### Фаза 2: UI Extraction (Coder)
- **Цель**: Создать визуальные блоки.
- **Файлы для создания**: 
    - `APP/src/components/sidebar.py`
    - `APP/src/components/employee_table.py`
    - `APP/src/components/stats_panel.py`
    - `APP/src/components/log_panel.py`
- **Валидация**: Создание экземпляров компонентов без ошибок.

### Фаза 3: Logic Extraction (Refactor)
- **Цель**: Отделить логику от UI.
- **Файлы для создания**: 
    - `APP/src/controllers/app_controller.py`
    - `APP/src/controllers/config_controller.py`
- **Валидация**: Unit-тесты для методов контроллеров (без GUI).

### Фаза 4: Integration (Coder)
- **Цель**: Собрать приложение заново.
- **Файлы для изменения**: `APP/src/gui_master.py`.
- **Валидация**: Успешный запуск приложения и сборка тестового отчета.

## 5. Оценка стоимости (Est. Cost)
| Фаза | Agent | Model | Est. Input | Est. Output | Est. Cost |
|-------|-------|-------|-----------|------------|----------|
| 1 | Architect | Pro | 8000 | 1500 | $0.14 |
| 2 | Coder | Pro | 10000 | 3000 | $0.22 |
| 3 | Refactor | Pro | 12000 | 3500 | $0.26 |
| 4 | Coder | Flash | 8000 | 2000 | $0.02 |
| **Всего** | | | | | **~$0.64 USD** |

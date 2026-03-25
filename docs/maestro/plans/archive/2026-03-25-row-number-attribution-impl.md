---
task_complexity: medium
---

# Implementation Plan: Fix Row Number Attribution

## Plan Overview
*   **Total Phases**: 2
*   **Agents Involved**: `coder`, `tester`
*   **Estimated Effort**: Low-Medium

## Execution Profile
- Total phases: 2
- Parallelizable phases: 0
- Sequential-only phases: 2

## Dependency Graph
Phase 1 (Code implementation)
  │
  ▼
Phase 2 (Validation & Test)

## Execution Strategy

| Phase | Agent | Description | Mode |
|-------|-------|-------------|------|
| 1 | `coder` | Добавление столбца `__original_row_idx__` в `consolidator.py` перед `dropna` и адаптация логики `transform_row` и тестов `test_consolidator.py`. | Sequential |
| 2 | `tester` | Запуск тестов `pytest` и `compare_march.py` для финальной проверки на реальных данных. | Sequential |

## Phase Details

### Phase 1: Code Implementation
*   **Objective**: Сохранить оригинальные индексы Excel до фильтрации пустых строк.
*   **Agent**: `coder`
*   **Files to Modify**:
    *   `APP/src/consolidator.py`: В функциях `process_file` и `consolidate_multiple` (или в соответствующем цикле) прямо перед строкой `df = df.dropna(...)` добавить вычисление нового столбца: `df['__original_row_idx__'] = df.index + header_idx + 2`. Внутри цикла, вместо `actual_row_idx = idx + 1`, использовать `actual_row_idx = row_dict.get('__original_row_idx__')`. Обновить передачу индекса в `self.transform_row(..., row_index=actual_row_idx, ...)`.
    *   `APP/tests/test_consolidator.py`: Обновить фикстуры и проверки, если они ожидают жестко заданные индексы.
*   **Dependencies**: `blocked_by`: []
*   **Validation**: Код успешно компилируется без синтаксических ошибок.

### Phase 2: Validation & Test
*   **Objective**: Подтвердить, что строки-призраки удаляются, а валидные строки получают правильный номер (например, для Адама стр. 10 вместо стр. 5).
*   **Agent**: `tester`
*   **Dependencies**: `blocked_by`: [1]
*   **Validation**: Успешное прохождение 100% юнит-тестов (`pytest APP/tests`). Успешный запуск скриптов: генерация `generate_march.py` и проверка `compare_march.py`.

## Cost Estimation
| Phase | Agent | Model | Est. Input | Est. Output |
|-------|-------|-------|-----------|------------|
| 1 | `coder` | `pro` | 5000 | 500 |
| 2 | `tester` | `flash` | 4000 | 200 |
| **Total** | | | **9000** | **700** |

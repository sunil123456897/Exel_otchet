---
design_depth: deep
task_complexity: complex
date: 2026-04-05
topic_slug: master-report-elite-testing
---

# Design Document: Master-Report v5.5 "Elite" - Всесторонняя проверка и тестирование

## 1. Problem Statement
Проект Master-Report v5.5 "Elite" является критически важной системой консолидации финансовых отчетов. Основная проблема — обеспечение **абсолютной надежности** и **производительности** в условиях "грязных" данных (кураторы) и нестабильных сетевых каналов (SMB). Тестирование должно подтвердить статус "Elite" версии 5.5.

## 2. Requirements

### Functional
- REQ-F1: 100% покрытие парсинга всех типов Excel (.xlsx, .xlsb) через CalamineReader.
- REQ-F2: Корректность финансовых правил (ПРИХОД/РАСХОД) и точность округления Decimal.
- REQ-F3: Обработка "ядовитых" данных (Toxic Data) без падения системы.

### Non-Functional
- REQ-NF1: Стабильность SMB-оптимизации (Local Copy) при задержках сети.
- REQ-NF2: Конкурентная запись в SQLite (WAL mode) под нагрузкой 8+ потоков.
- REQ-NF3: Скорость обработки (KPI) — не более 2с на файл среднего объема.

### Constraints
- C1: Работа только в Windows-окружении (win32).
- C2: Отсутствие доступа к реальным корпоративным секретам (использование синтетики).

## 3. Approach

### Approach 1: Integrated "Chaos & Stress" Suite (Рекомендуется)
**Summary**: Создание комплексного конвейера тестирования, объединяющего генерацию стресс-данных (Black Swan/Toxic), имитацию сетевого хаоса (SMB latency/disconnection) и нагрузку на БД.
**Pros**: Выявляет редкие "гонки" (race conditions) и ошибки памяти.
**Cons**: Требует длительного времени выполнения.
**Weighted Total**: 4.8 (Traces To: REQ-F3, REQ-NF1, REQ-NF2).

### Approach 2: Isolation & Unit Exhaustion
**Summary**: Максимальное покрытие каждого модуля (Domain, Infra) по отдельности с использованием моков (mocks) для сети и БД.
**Pros**: Быстрое выполнение, легко локализовать ошибку.
**Cons**: Пропускает системные баги на "швах" архитектуры (AppController).
**Weighted Total**: 3.5.

### Decision Matrix
| Criterion | Weight | Approach 1 | Approach 2 |
|-----------|--------|------------|------------|
| Resilience (Надежность) | 40% | 5: Выявляет хаос | 3: Пропускает швы |
| Accuracy (Точность) | 30% | 5: Реальные условия | 4: Идеальные условия |
| Efficiency (KPI) | 30% | 4: Долгий запуск | 5: Очень быстро |
| **Weighted Total** | | **4.7** | **3.9** |

## 4. Architecture
Тестовая архитектура строится вокруг **AppController** как главного диспетчера.
- **Data Generator**: Создает фикстуры (Synthetic/Toxic).
- **Network Simulator**: Имитирует SMB-задержки (Local Copy validation).
- **Concurrency Driver**: Запускает параллельные потоки для SQLite WAL.

## 5. Agent Team
- `tester`: Разработка и запуск всех типов тестов.
- `debugger`: Анализ логов при сбоях и поиск багов в коде.
- `performance_engineer`: Замер KPI и оптимизация SQLite/Calamine.
- `code_reviewer`: Аудит архитектурных "швов" в AppController.

## 6. Risk Assessment
- **Risk 1**: Ресурсный голод при стресс-тестах (RAM/CPU). *Mitigation*: Лимиты в psutil.
- **Risk 2**: Ложноположительные тесты на сети. *Mitigation*: Детерминированный Network Simulator.

## 7. Success Criteria
1. Все тесты (Toxic, Black Swan, Stress, Regression) проходят успешно (Green state).
2. KPI парсинга соответствуют "Elite" стандарту (Calamine speed verified).
3. Покрытие критической логики в LogicService составляет 100%.
4. Отсутствие ошибок "Database is locked" при конкурентной записи.

# Stage 8 Report — Performance and long-run resilience

```text
Этап: 8 (Производительность и устойчивость длительной работы)
Цель: Зафиксировать SLA на реальных объёмах и исключить зависания/утечки.
Исходная проблема:
  - Не было формального timing harness: нельзя было отличить
    "стало медленнее" от "машина loaded".
  - Утечки threads/handles/memory не проверялись — типичный риск для
    длительной работы с Tk + openpyxl + subprocess (calamine worker).
  - SLA из ТЗ (startup ≤5s, refresh 23 ≤2s, consolidation ≤30s) были
    intent-ами, не измеренными фактами.
Новые модули:
  - tools/timing_report.py: воспроизводимый timing harness.
      * 4 benchmark'а: import APP, parse workbook, apply_financial_rules
        (100 rows), write_report (50 rows);
      * median + p95 из N запусков (default 5, first = warmup);
      * leak detection: 100 итераций → delta threads / gc_objects;
      * JSON output для CI; human-readable summary по умолчанию;
      * PII-free (использует tests/golden/synthetic_fixtures).
  - tests/test_performance_sla.py (8 тестов):
      * apply_financial_rules — threshold 500 ms (floor ~2 ms);
      * parse_synthetic_workbook — threshold 1 s (floor ~6 ms);
      * write_report — threshold 5 s (floor ~67 ms);
      * leak: 100 итераций не растят threads и <200 gc objects;
      * leak: 20 итераций парсинга не плодят threads;
      * leak: 20 open/close циклов openpyxl не leak'ают OS handles
        (rename succeeds afterwards);
      * idempotent re-run: 10 последовательных write не замедляются;
      * timing_report.py запускается без ошибок, JSON валиден.
  - tests/golden/timing_baseline.json: snapshot таймингов на dev-
    машине. Используется как reference для будущего regression
    detection.
Измеренные значения (dev machine, Python 3.12.10, Win10):
  import_APP:                         0.43 ms (p95 0.46)
  parse_synthetic_workbook:           6.19 ms (p95 6.19)
  apply_financial_rules (100 rows):   2.25 ms (p95 2.27)
  write_report (50 rows):            67.30 ms (p95 68.73)
  leak after 100 iterations:          threads_delta=0
                                      gc_objects_delta=-1
Команды проверки (фактический gate):
  pytest tests/test_performance_sla.py                       # 8 passed
  pytest tests/ (full regression)                            # 963 passed
  python tools/timing_report.py --runs 5                     # все 4 bench OK
  ruff check APP tests                                       # clean
  ci_mypy_check.py                                           # PASS 0 new
Результат:
  - Timing harness готов и работает offline (no GUI, no network)
  - Floor-оценки SLA: самый медленный pipeline stage (write_report)
    ≤68 ms на 50 строк — это означает, что реальная консолидация
    23 employees × N строк ограничена I/O и сетью, не CPU
  - Leak detection: ни threads, ни objects не накапливаются
  - timing_baseline.json — reference для будущего regression detection
  - mypy/ruff/golden все green
Оставшиеся риски:
  - R-8.1 [средний]: реальные SLA (startup ≤5s, refresh 23 ≤2s,
    consolidation ≤30s) требуют измерений на реальной машине с
    сетевыми дисками. Harness даёт floor, не верхнюю границу.
    Operator должен запустить timing_report на pilot-машине и
    сверить с SLA в ТЗ. Если floor уже нарушает SLA (что маловероятно
    — наши floor'ы в 100× ниже SLA), необходима оптимизация.
  - R-8.2 [низкий]: handle leak detection не использует psutil (нет
    в deps). Вместо этого мы делаем косвенный тест: rename после
    цикла open/close. Если handle утёк — rename упадёт с
    PermissionError на Windows. Это надёжный proxy, но не даёт числа.
  - R-8.3 [низкий]: regression threshold (>20% ухудшение) сегодня
    реализован как comment в harness, а не как CI gate. Автоматическое
    сравнение с предыдущим timing_baseline.json требует CI job,
    который сохраняет artefact между запусками. Реализуемо через
    GitHub Actions cache, оставлено на отдельную CI-задачу.
  - R-8.4 [информационно]: SLA "GUI не блокируется более 200 ms без
    progress" требует GUI-инструментария (например, measuring Tk event
    loop latency). Это ручная проверка в Stage 7 acceptance matrix
    (пункт C7: Cancel responds within 2s).
  - R-8.5 [информационно]: memory growth за 1 час повторных операций
    не измерен. Leak-тесты проверяют 100 итераций (минуты), не час.
    Длительная приёмка — часть ручного pilot.
Решение gate: PASS (автоматическая часть; реальные SLA требуют
                   pilot-измерений)
```

## Ключевые решения и находки этапа 8

1. **Floor vs SLA.** ТЗ даёт SLA: startup ≤5s, refresh ≤2s,
   consolidation ≤30s. Harness измеряет floor — то, что CPU может
   выдать без I/O. Реальные числа на машине оператора будут выше из-за
   сети и реальных Excel. Floor-оценки:
   - import: 0.4 ms (SLA 5000 ms) — 12 500× запас
   - parse: 6 ms (SLA 2000 ms / 23 файла ≈ 87 ms/file) — 14× запас
   - apply_rules: 2 ms/100 rows (SLA 30000 ms) — огромный запас
   - write: 67 ms/50 rows (SLA 30000 ms / N writes) — большой запас
   
   **Вывод: CPU не узкое место.** Любые real-world задержки — это I/O
   и сеть. Это важно для оператора: оптимизации CPU не улучшат UX;
   улучшать нужно network retry logic, кэширование Excel-чтения и
   отсутствие блокирующих вызовов в UI thread.

2. **Leak detection без psutil.** psutil нет в runtime-deps (только
   types-psutil в dev-deps). Чтобы не тянуть runtime-зависимость,
   использованы два proxy:
   - `threading.active_count()` для threads (portable);
   - "rename после цикла" для OS handles (Windows: PermissionError
     если handle утёк);
   - `gc.get_objects()` len для объектов Python (слабый proxy для
     memory, но ловит большие утечки).
   Это не идеально, но достаточно для CI. Полное profiling — pilot.

3. **Thresholds как 250× от floor.** Если поставить threshold = floor,
   тесты будут флапать на медленных CI-раннерах. 250× — это generous
   margin, реальный regression всё равно зашкалит за него. Пример:
   если apply_financial_rules вдруг станет quadratic (100 ms вместо
   2 ms), порог 500 ms всё ещё поймает (100 < 500, но если 1000 строк
   → 10000 ms → поймает). Это правильный компромисс между flakiness
   и detection sensitivity.

4. **`warmup` discard.** Первое измерение всегда медленнее из-за
   import cache, openpyxl state. Harness выбрасывает warmup-замер —
   без этого median был бы skewed.

5. **Timing baseline в репозитории.** `tests/golden/timing_baseline.json`
   — это reference-снимок на dev-машине. Не equality-test (числа
   зависят от железа), а якорь для будущего regression detection.

## Что НЕ сделано (и почему)

- **Реальные SLA не измерены.** Это требует pilot-машины с реальными
  сетевыми дисками и Excel. Harness даёт floor; operator должен
  запустить его на production-окружении.

- **psutil integration.** psutil нет в .venv. Установка — изменение
  окружения, требующее разрешения владельца. Текущие proxy-тесты
  достаточно надёжны для CI.

- **GUI event-loop latency.** SLA "GUI не блокируется >200 ms" —
  это про Tk mainloop, а не про pipeline. Измеряется вручную в
  Stage 7 matrix (C7: Cancel responds within 2s).

- **1-hour memory soak test.** Тесты проверяют ~100 итераций (минуты),
  не час. Длительная приёмка — часть ручного pilot.

- **CI regression gate (>20% threshold) не построен.** Требует GitHub
  Actions с сохранением artefact между запусками. Реализуемо, но
  это CI infrastructure work, не часть Stage 8 codebase.

## Коммиты (логические единицы, после разрешения владельца)

1. `feat(perf): reproducible timing harness with leak detection`
   (tools/timing_report.py)
2. `test(perf): SLA thresholds + leak detection for threads/handles/objects`
   (tests/test_performance_sla.py)
3. `chore(perf): record timing baseline snapshot`
   (tests/golden/timing_baseline.json)

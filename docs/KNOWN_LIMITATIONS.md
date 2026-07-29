# Known Limitations

**Version:** 5.6 (Stage 0–9 complete)
**Date:** 2026-07-21
**Purpose:** явный список того, что НЕ сделано или имеет сознательные
ограничения. Каждое ограничение имеет причину и mitigation. Любое
из них может быть снято в будущей работе.

Этот документ — часть Definition of Done для Stage 10 (документация).
Подпись заказчика на pilot подразумевает согласие с этим списком.

## Категория A: Требует ручной проверки (не автоматизируется в CI)

### A1. Реальные SLA не измерены
- **Что:** ТЗ определяет SLA (startup ≤5s, refresh 23 ≤2s, consolidation
  ≤30s). Harness даёт floor-оценки, но не upper bound на реальной машине.
- **Причина:** CI не имеет реальных сетевых дисков, реальных Excel,
  configurable DPI дисплея.
- **Mitigation:** operator запускает `tools/timing_report.py` на
  pilot-машине и сверяет с SLA. Floor-оценки в 100-1000× ниже SLA.
- **Stage 8 R-8.1.**

### A2. Windows UI acceptance matrix не заполнен
- **Что:** Stage 7 создал формальный чек-лист (~50 пунктов) для ручной
  проверки на Windows 10/11. Он должен быть выполнен QA перед pilot.
- **Причина:** DPI rendering, Excel version compatibility, real network
  drive latency — всё это требует человеческого восприятия или реальной
  среды.
- **Mitigation:** `docs/archive/stage_reports/stage_7_acceptance_matrix.md`.
- **Stage 7 R-7.1.**

### A3. Pilot не проведён
- **Что:** ТЗ требует 2 пилотных пользователя на 5–10 рабочих дней.
- **Причина:** pilot — это реальная работа в фирме, не автоматизация.
- **Mitigation:** только после подписания acceptance matrix.

## Категория B: Сознательные ограничения дизайна

### B1. Updater не подключён к BAT (Stage 4)
- **Что:** Полноценный Python-updater (Stage 4) реализован и протестирован,
  но `tools/update_from_github.ps1` остаётся рабочим путём.
- **Причина:** Wiring требует UI-интеграции (Stage 7 followup); принудительное
  переключение — рискованное изменение runtime-пути.
- **Mitigation:** operator может opt-in через BAT, когда будет готов.

### B2. psutil не в dependencies
- **Что:** Leak-detection использует proxy-тесты (threading.active_count,
  rename-after-cycle), а не psutil.
- **Причина:** psutil — runtime dependency. Установка требует явного
  разрешения владельца.
- **Mitigation:** Proxy-тесты надёжны для CI. Полное profiling — pilot.
- **Stage 8 R-8.2.**

### B3. Standalone-сборка (PyInstaller) — Stage 12
- **Что:** Распространение через Python-source + .venv. Standalone EXE
  отложен.
- **Причина:** Stage 12 требует письменного разрешения владельца.
- **Mitigation:** ТЗ «без защиты» явно исключает этот этап.

### B4. Authenticode, лицензирование, обфускация — Stage 12
- **Что:** Все меры защиты продукта отложены.
- **Причина:** Stage 12 требует отдельного ТЗ и разрешения владельца.
- **Mitigation:** ТЗ «без защиты» явно исключает.

## Категория C: Частично выполненные задачи

### C1. mypy strict — domain + services clean, остальное в baseline
- **Что:** Из 312 нормализованных mypy-находок исправлено 9 (312→303).
  domain и services полностью clean; app/controller, UI, infra/{export,
  reconciliation, rsch} остаются в baseline.
- **Причина:** ТЗ закладывает 7-10 дней на mypy; одна сессия покрыла
  приоритетную часть.
- **Mitigation:** mypy gate (Stage 0) блокирует новые ошибки. Дальнейшая
  чистка — инкрементальная.
- **Stage 5 R-5.1.**

### C2. Coverage% не измеряется
- **Что:** pytest-cov отсутствует в .venv. Пороги покрытия из ТЗ нельзя
  вычислить.
- **Причина:** Установка пакета — изменение окружения, требует разрешения.
- **Mitigation:** risk-based test matrix: для каждой критической функции
  есть property-based + fault-injection + example-based тесты.
- **Stage 0 R-0.1, Stage 6 R-6.3.**

### C3. ruff I001/B/SIM/UP не применены массово
- **Что:** ruff проверяет только E/F (clean). I001 откатан — вскрыл
  скрытый circular import.
- **Причина:** I001/B/SIM/UP имеют 1000+ находок; применение "одним
  коммитом" рискованно.
- **Mitigation:** поэтапное внедрение.
- **Stage 5 R-5.4.**

## Категория D: Известные технические долги

### D1. Скрытый circular import в core.infra.__init__ ↔ export_writer
- **Что:** ruff I001 вскрыл circular import, который маскируется порядком
  импортов.
- **Причина:** Рефакторинг export_writer (вынести is_file_writable) —
  отдельная задача.
- **Mitigation:** порядок импортов вручную; regression detection через
  архитектурные тесты (Stage 5).
- **Stage 5 R-5.3.**

### D2. 16 messagebox.showerror(..., str(e)) call-sites остаются
- **Что:** Часть call sites не мигрированы на `present_error`. Они могут
  течь `str(exc)`.
- **Причина:** Инкрементальная работа; каждая правка требует проверки
  на real leak.
- **Mitigation:** present_error доступен; новые call sites должны его
  использовать.
- **Stage 7 R-7.3.**

### D3. L2 functional smoke в updater — skipped
- **Что:** Self-check L2 (golden smoke в staging) помечен skipped.
- **Причина:** Требует golden-test infra (готова после Stage 5), но
  wiring — отдельная задача.
- **Mitigation:** L0 + L1 работают; L2 добавляется без изменения
  архитектуры.
- **Stage 4 R-4.2.**

### D4. classify_sheet_date не wired в pipeline
- **Что:** Функция готова, но не вызывается в ingestion.
- **Причина:** Интеграция — behaviour change (появится warning для
  каждого листа); UI (Stage 7) должен показать его.
- **Mitigation:** Функция готова; вызов можно добавить без переделки.
- **Stage 3 R-3.2.**

### D5. config_wizard не построен
- **Что:** TZ MR-0701 упоминает «мастер создания/проверки конфигурации».
  First-run detection есть, но wizard с выбором путей — нет.
- **Причина:** Большая UI-работа, выходящая за рамки одной сессии.
- **Mitigation:** Существующий Settings tab даёт функциональность, просто
  не как wizard.
- **Stage 7 R-7.2.**

## Категория E: Manual-only процедуры

### E1. Сборка diagnostic_package.zip — отдельный шаг
- **Что:** Runbook описывает процесс через `ДИАГНОСТИКА.bat`, но
  packaging требует ручного запуска `tools/diagnostic_package.py`.
- **Mitigation:** Wiring — Stage 11 rehearsal.
- **Stage 9 R-9.4.**

### E2. Anonymise Excel — ручная процедура
- **Что:** Runbook упоминает «обезличенный образец Excel», но нет
  инструмента для автоматической чистки имён и сумм.
- **Mitigation:** Operator делает вручную. Будущая работа —
  `tools/anonymise_excel.py`.
- **Stage 9 R-9.5.**

### E3. Screenshot baseline (TZ MR-0704) — не построен
- **Что:** Baseline-скриншоты ключевых состояний UI не созданы.
- **Причина:** Требует решения о screen capture framework и storage.
- **Mitigation:** Оставлено на отдельную сессию.
- **Stage 7 (в карточке).**

---

## Подписи

Принятие этого списка ограничений — необходимое условие для pilot.

| Роль | Имя | Дата | Принимает ограничения |
|------|-----|------|----------------------|
| Владелец |   |   |   |
| Разработчик |   |   |   |
| Pilot user 1 |   |   |   |
| Pilot user 2 |   |   |   |

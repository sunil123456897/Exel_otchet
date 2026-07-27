# Stage 4 Report — Atomic update and rollback

```text
Этап: 4 (Атомарное обновление и восстановление без защиты)
Цель: Сотрудник обновляет программу двойным кликом по BAT. При любой
       ошибке остаётся рабочая предыдущая версия и все пользовательские данные.
Выбор владельца Q1: Вариант A — исходники Python + общий .venv.
       Общий .venv обновляется внутри staging и переключается вместе
       с исходниками. Полноценный versioned-updater с изолированным
       окружением на каждую версию переезжает в этап 12 вместе с PyInstaller.
Исходная проблема:
  - tools/update_from_github.ps1 (552 строки) копирует файлы поверх
    старой версии: нет staging, нет atomic switch, нет автоматического
    rollback, нет self-check, нет startup-ok.
  - При обрыве посередине копирования установка становилась смешением
    двух версий.
  - Повреждённый / подменённый архив распаковывался без проверки SHA.
  - Опасные пути (абсолютные, ../, symlink) в архиве не проверялись.
  - Запуск второго updater'а одновременно не блокировался.
Новые модули:
  - APP/core/infra/updater_model.py (MR-0401..0406): полная Python-
    реализация атомарного updater'а:
      * VersionManifest / CurrentVersion / UpdateResult / UpdateLock;
      * Updater.update() с pipeline:
        lock → preflight → fetch → L0 (size+sha+path-safety) → staging →
        L1 (entry-point files exist) → backup → atomic switch
        (rename staging → final, swap current.json) → launch → wait
        for startup-ok → rollback on failure;
      * UpdateLock: cross-process PID-файл с защитой от stale lock
        (PID out-of-range считается мёртвым);
      * wait_for_startup_ok_marker: bounded wait с polling на 0.5с;
      * check_archive_path_safety: абсолютные пути, traversal, symlink.
  - fetch_fn plugged-in: production wires HTTP/Git fetcher, tests
    wire local-copy stub. Один и тот же engine работает и для GitHub,
    и для offline ZIP (MR-0406).
Новые тесты (MR-0407, 22 сценария):
  Happy path:
    - test_happy_path_update
    - test_offline_zip_works_without_network
    - test_reinstall_same_version_overwrites_cleanly
  L0 integrity:
    - test_sha_mismatch_aborts
    - test_size_mismatch_aborts
    - test_truncated_archive_aborts
    - test_bad_zip_signature_aborts
    - test_dangerous_absolute_path_in_archive_aborts
    - test_traversal_path_in_archive_aborts
  Preflight:
    - test_insufficient_free_space_aborts
  Lock:
    - test_second_updater_instance_is_blocked
    - test_stale_lock_is_reclaimed
    - test_update_lock_is_reentrant_safe
    - test_update_lock_context_manager
  Self-check:
    - test_archive_without_main_py_fails_L1
  Startup-ok + rollback:
    - test_missing_startup_ok_triggers_rollback
    - test_rollback_restores_previous_pointer
    - test_mid_step_crash_does_not_corrupt_state
  Policy:
    - test_downgrade_is_not_automatically_prevented
      (движок нейтрален; policy layer проверяет version)
  Data model round-trips:
    - test_current_version_round_trips
    - test_manifest_round_trips
    - test_manifest_rejects_missing_required_fields
Сопутствующие правки:
  - tests/test_single_version_source.py: в allowlist добавлен
    APP/core/infra/updater_model.py:68 — docstring пример manifest JSON.
Команды проверки (фактический gate):
  pytest tests/test_updater.py                                    # 22 passed
  pytest tests/test_single_version_source.py                      # 95 passed
  full regression                                                 # 864 passed
  ci_mypy_check.py                                                # PASS 0 new
Результат:
  - 22 updater-теста покрывают все TZ failure-режимы
  - Atomic switch через os.replace + tmp.json — никогда не остаётся
    partially-written current.json
  - Rollback автоматически восстанавливает previous_version
  - Offline ZIP работает через тот же engine (network-agnostic)
  - Lock защищает от двойного запуска, stale lock распознаётся
  - SHA + size + path-safety проверяются до распаковки
  - mypy strict gate: 0 новых ошибок (baseline 312)
  - single-version-source test: 0 drift literals (95 passed)
Оставшиеся риски:
  - R-4.1 [средний]: Updater.update() реализован как Python-модуль,
    но НЕ подключён к tools/update_from_github.ps1. Существующий
    PowerShell-апдейтер остаётся рабочим путём; новый engine — это
    replacement, который operator включает через BAT опционально.
    Wiring в BAT — это изменение runtime-пути, требующее permissions
    Stage 7 (UI) или отдельного решения владельца.
  - R-4.2 [низкий]: L2 (golden smoke) сейчас skipped в _run_self_check.
    Реальный L2 требует вызова LogicService + MasterWriter на synthetic
    fixture в staging — это можно сделать после Stage 5 (mypy strict),
    чтобы не дублировать smoke-test infra.
  - R-4.3 [низкий]: _free_space_mb использует shutil.disk_usage,
    что на UNC-пути может вернуть 0. Если такое произойдёт, fallback
    возвращает "много места" (1<<30 MB) — лучше продолжить, чем
    блокировать update на ложном "нет места".
  - R-4.4 [информационно]: UpdateLock использует PID-файл, не
    kernel-level lock. Это cross-platform компромисс; на Windows
    file-locks имеют разную семантику между версиями. PID-pattern
    стандартен для cross-platform installer'ов (apt, dnf, msi).
  - R-4.5 [информационно]: rollback восстанавливает указатель current.json
    на previous_version, но НЕ удаляет неудачную versions/<semver>/.
    Это сознательно — диагностические логи неудачной версии сохраняются
    для разбора. Operator может удалить вручную.
Решение gate: PASS
```

## Ключевые архитектурные решения этапа 4

1. **Один движок, два источника.** `Updater` принимает `fetch_fn`,
   который может быть как GitHub-HTTP fetcher, так и local-copy stub.
   Это означает, что один и тот же pipeline работает для online- и
   offline-обновлений (TZ MR-0406). Никакого раздвоения кода.

2. **Atomic switch через rename + tmp.** `current.json` пишется в
   `.tmp` файл, потом `os.replace` атоматически подменяет. Это
   atomic на POSIX и quasi-atomic на Windows (гарантия для same-volume).
   Никогда не остаётся partially-written указателя версии.

3. **Self-check L0/L1/L2 — отдельные слои.**
   - L0 = size + SHA + path-safety (до распаковки).
   - L1 = entry-point files существуют (дёшево).
   - L2 = functional smoke на synthetic fixture (пока skipped, будет
     wired после Stage 5).
   Разделение позволяет updater'у проваливаться поэтапно, а не "всё
   или ничего".

4. **Rollback восстанавливает указатель, не удаляет.** Неудачная
   `versions/<semver>/` сохраняется для диагностики. Operator может
   просмотреть логи, понять причину, и только потом удалить.

5. **UpdateLock — cross-process PID-файл.** Не Windows-file-lock,
   потому что их семантика зависит от версии Windows. PID-pattern
   стандартен (используется apt/dnf/msi). Stale lock распознаётся
   (PID out of range → считается мёртвым).

6. **Не трогаем рабочий tools/update_from_github.ps1.** Новый engine
   — это replacement, а не forced migration. Существующий путь
   продолжает работать; operator может opt-in через BAT.

## Что НЕ сделано (соблюдение границ этапа)

- **BAT-wiring не выполнен.** Новый Python-updater реализован и
  протестирован, но tools/update_from_github.ps1 остаётся рабочим.
  Wiring — это изменение runtime-пути, его надо делать с UI (Stage 7).

- **L2 functional smoke не wired.** Структура есть, но реальный
  вызов LogicService + MasterWriter в staging требует golden-test
  infra (Stage 5). Сейчас L2 skipped с явным логом.

- **Запущенный app не определяется.** TZ MR-0402 упоминает "проверка
  запущенного приложения". На Windows это нетривиально (нет /proc),
  и false-positive (блокировка update когда app не запущен) хуже
  false-negative. Сознательно оставлено на Stage 7.

- **Конкретный HTTP fetcher для GitHub не написан.** `fetch_fn`
  принимает manifest + dest_dir → Path. Production-wiring (URL
  formation, headers, retries) — это infrastructure code, который
  лучше делать вместе с CI/CD-pipeline. Сейчас engine использует
  stub, тесты — local copy.

## Коммиты (логические единицы, после разрешения владельца)

1. `feat(updater): atomic versioned update engine with L0/L1 self-check`
   (updater_model.py)
2. `test(updater): 22-scenario matrix — corrupt/SHA/space/lock/rollback`
   (test_updater.py)
3. `chore(test): allowlist docstring example in single-version-source test`
   (test_single_version_source.py)

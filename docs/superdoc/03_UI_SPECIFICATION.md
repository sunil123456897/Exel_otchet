# UI-спецификация Master-Report v5.6 — СЛОЙ 2a

> **Тип документа (Divio):** Reference. Сухой, табличный, попиксельный.
> **Источник истины:** исходники `APP/core/ui/*.py`. При рассинхроне **код выигрывает**.
> **Связанные документы:** `02_DESIGN_SYSTEM.md` (токены, поведение цвета/анимаций) — тут только то, что привязано к конкретному виджету.
>
> **Аудитория:** QA-инженеры (визуальная регрессия), разработчики-интеграторы, технические ревьюеры.
> **Цель:** по каждой карточке видно «как выглядит, где стоит, на что реагирует, где определён».

---

## Как читать карточку

Каждый компонент описан одной карточкой со следующими полями:

| Поле | Что содержит |
|---|---|
| **Назначение** | 1 предложение: что виджет делает |
| **Расположение** | layout-позиция + размеры (`fill/expand`, width/height, pack-сторона) |
| **Цвета** | токены из `ThemeManager.COLORS`, в формате `bg=bg_sidebar / fg=text` для light И dark |
| **Шрифт** | токен из `ThemeManager.FONTS` |
| **Padding/Spacing** | токен из `SPACING`/`CONTROL`, с указанием множителя плотности |
| **Состояния** | переходы цветов (`hover: bg → border_subtle`) |
| **События** | bind и виртуальные события |
| **Command/callback** | что вызывает |
| **Зависимости** | что перерисовывать при `set_theme` (реестр `register`/`refresh_theme`) |

Сокращения: `L` = light, `D` = dark. Цвета вида `L:#fff` / `D:#171b21`. Полные hex-значения токенов — в `02_DESIGN_SYSTEM.md`.

---

## ASCII-схема: главное окно

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [_][□][×]   Master-Report v5.6 — {date} — {operation} {progress}%        │  ← Tk root (titlebar)
├────────────────────┬─────────────────────────────────────────────────────┤
│ 📊 ПАНЕЛЬ          │  main_area (Main.TFrame, padding=15)                 │
│ 🟢 Сеть: n/n       │ ┌─────────────────────────────────────────────────┐  │
│ ┌📅 ВЫБОР ДАТЫ──┐  │ │ [Сотрудники] [Панель] [Отчеты] [📜 История] …   │  │  ← TNotebook
│ │ [DateEntry]🔄│  │ ├─────────────────────────────────────────────────┤  │
│ └──────────────┘  │ │                                                  │  │
│ ┌👤 СОТРУДНИКИ─┐  │ │   активная вкладка (TFrame, padding=12)          │  │
│ │ ➕ Добавить  │  │ │                                                  │  │
│ │ 📎 Привязать │  │ │   EmployeeTable / results_tree / reports_tree /  │  │
│ └──────────────┘  │ │   history_tree / diagnostics_tree / log Text /   │  │
│ ┌🚀 СБОРКА─────┐  │ │   AliasesTab                                    │  │
│ │ Куратор: [▾] │  │ │                                                  │  │
│ │ ⚡ СОБРАТЬ ДЕНЬ│  │ │                                                  │  │
│ │ 🌍 ВСЕ ДАТЫ  │  │ │                                                  │  │
│ │ 🧾 РСЧ       │  │ │                                                  │  │
│ │ ✅ СВЕРИТЬ   │  │ │                                                  │  │
│ │ ✅ АВТОСВЕРКА│  │ │                                                  │  │
│ └──────────────┘  │ │                                                  │  │
│ ▶  📆 ЗА ПЕРИОД    │ │                                                  │  │
│   (collapsible)   │ │                                                  │  │
│ ┌🎨 ТЕМА──────┐   │ │                                                  │  │
│ │ ☀ Светлая   │   │ │                                                  │  │
│ │ 🌙 Тёмная    │   │ │                                                  │  │
│ │ 💻 Системная │   │ │                                                  │  │
│ └──────────────┘  │ │                                                  │  │
│ ⚙ НАСТРОЙКИ       │ │                                                  │  │
│ ⌨ ГОРЯЧИЕ КЛАВИШИ │ │                                                  │  │
│ ┌📈 СТАТИСТИКА─┐  │ │                                                  │  │
│ │ Готовность ▓▓│  │ │                                                  │  │
│ │ Операция ▓▓▓▓│  │ │                                                  │  │
│ └──────────────┘  │ └──────────────────────────────────────────────────┘  │
│ ↑ canvas+scrollbar (внутри Sidebar)                                       │
└────────────────────┴─────────────────────────────────────────────────────┘
                                        ↑ Toasts складываются в правый нижний угол
```

**Layout-слои:**
1. `root` (`tk.Tk`, bg=`bg_main`) — принимает `Sidebar` (LEFT, fill=Y) и `main_area` (RIGHT, fill=BOTH, expand).
2. `Sidebar` (Sidebar.TFrame, width=240–380) — внутри Canvas + Scrollbar + `content` Frame.
3. `main_area` (Main.TFrame, padding=15) — содержит `notebook` (fill=BOTH, expand).
4. `StatsPanel` — упакован в `sidebar.content` (прокручивается вместе с настройками).

**Источник:** `gui_master.py:274-319` (`setup_ui`).

---

## Часть A. Window Chrome

### A1. Окно `GuiMaster` (root `tk.Tk`)

| Поле | Значение |
|---|---|
| **Назначение** | Корневое окно приложения, контейнер для Sidebar + main_area |
| **Расположение** | top-level window; центрируется на экране |
| **Title** | `Master-Report v5.6 \| Financial Consolidator` (idle); при операции — `Master-Report v5.6 — {date} — {label} {progress}%` |
| **Geometry** | default `1100×840`, fitted до 82% ширины/88% высоты экрана через `_fit_window_geometry` |
| **minsize** | `max(640, sw*0.5) × max(420, sh*0.5)` — `gui_master.py:83` |
| **Icon** | `APP/assets/icons/app.ico` (предпочтение, `iconbitmap`) → fallback `app.png` (`iconphoto`). Пропускает `TclError` молча. `gui_master.py:204-226` |
| **Цвета** | bg = `bg_main` (L:`#f5f6f8` / D:`#111418`) — переустанавливается при каждой смене темы в `set_theme` |
| **DPI-awareness** | `ThemeManager.init_scaling(root)` (`gui_master.py:78`) — вычисляет `_scale ∈ [0.72, 2.0]` |
| **Resize-слушатель** | `ThemeManager.attach_resize_listener(root)` — debounce 120мс, пересчитывает scale по ширине окна |
| **Persist-geometry** | `load_geometry()` → `is_geometry_visible()` → fallback `_fit_window_geometry`. Сохранение: `save_geometry()` на `WM_DELETE_WINDOW` и на `<Destroy>` (двойная защита). `gui_master.py:462-504` |
| **Poll-title** | `_poll` каждые 500мс во время операции, 5000мс в idle. `gui_master.py:134-146` |
| **Poll-ОС-темы** | `_poll_system_theme` каждые 5000мс, активен только если `theme_var == "system"`. `gui_master.py:528-543` |
| **Горячие клавиши** | 9 привязок в `_bind_shortcuts` (`gui_master.py:228-272`) — см. A2 |
| **Зависимости** | `ThemeManager.set_theme` → перерисовывает `employee_table`, `dashboard_tabs`, `sidebar` через `refresh_theme()` |

### A2. Глобальные горячие клавиши (`_bind_shortcuts`)

| Клавиша | Действие | Hotkey-guard |
|---|---|---|
| `Ctrl+D` | `run_consolidation` (сборка за день) | да |
| `Ctrl+Shift+D` | `run_consolidation_all_dates` | да |
| `Ctrl+M` | `run_consolidation_month` (период) | да |
| `Ctrl+R` | `run_rsch_report` (РСЧ за день) | да |
| `Ctrl+Shift+R` | `run_rsch_report_month` | да |
| `Ctrl+E` | `run_reconciliation_report` (сверка) | да |
| `F5` | `refresh_status` | да |
| `Escape` | `_request_cancel` (отмена операции) | да |
| `F1` | `show_shortcuts` (диалог клавиш) | да |

**Hotkey-guard** (`gui_master.py:243-254`): если фокус в виджете класса `Entry` / `Text` / `TEntry` / `TCombobox` — горячая клавиша не перехватывается, чтобы не ломать нативное поведение каретки.

---

## Часть B. Sidebar

> Источник: `APP/core/ui/ui_sidebar.py`. Ширина: `sidebar_min=240` … `sidebar_max=380`, вычисляется как `screen_w × {0.20/0.22/0.24}` по viewport_mode (`ui_sidebar.py:423-434`).

### B1. Sidebar (контейнер, `Sidebar.TFrame`)

| Поле | Значение |
|---|---|
| **Назначение** | Левая панель навигации и сборки, скроллируемая |
| **Расположение** | `root` → `pack(side=LEFT, fill=Y)`. `pack_propagate(False)` фиксирует ширину |
| **Размер** | width = `max(260, min(360, int(screen_w × 0.22)))` на старте (`ui_sidebar.py:38`), пересчитывается на change-scale |
| **Цвета** | bg = `bg_sidebar` (L:`#ffffff` / D:`#171b21`) |
| **Padding** | `SPACING.xs` (=4) |
| **Структура** | `scroll_host` (Sidebar.TFrame) → `Canvas` (LEFT, fill=BOTH, expand) + `Scrollbar` (RIGHT, fill=Y) → `content` Frame (create_window) |
| **Canvas** | `borderwidth=0`, `highlightthickness=0`, bg=`bg_sidebar`. Зарегистрирован: `ThemeManager.register(canvas, bg_key="bg_sidebar", fg_key=None)` (`ui_sidebar.py:62`) |
| **Mousewheel** | bind на `<Enter>`/`<Leave>` Canvas (не `bind_all`) — `<MouseWheel>`, `<Button-4>`, `<Button-5>` (X11). `ui_sidebar.py:81-112` |
| **События** | `<Configure>` на content (`_on_content_configure` — scrollregion) и на canvas (`_on_canvas_configure` — ширина окна) |
| **Зависимости** | `ThemeManager.register` для Canvas; `add_scale_listener` для пересчёта ширины |

### B2. Индикатор сети (`tk.Label`)

| Поле | Значение |
|---|---|
| **Назначение** | Показывает доступность сетевых дисков (UX-017) |
| **Расположение** | `content`, `pack(anchor=W, pady=(0, SPACING.xs))` |
| **Цвета** | bg = `bg_sidebar`; fg = `text_muted` (L:`#6b7588` / D:`#8b94a5`) |
| **Шрифт** | `micro` (`("Segoe UI", 8)`) |
| **Текст-форматы** | `🟢 Сеть: n/n дисков доступны` (все) · `🟡 Сеть: n/n` (частично) · `🔴 Сеть: n/n` (нет) · `🟡 Сеть: нет дисков` / `нет конфиг` / `ошибка проверки` |
| **Poll** | первый через `after(2000)`, затем каждые **30 000мс** через `_poll_network_drives`. Пробы `os.path.exists` на daemon-thread (чтобы не морозить GUI при SMB-timeout) |
| **Зависимости** | `ThemeManager.register(label, bg_key="bg_sidebar", fg_key="text_muted")` (`ui_sidebar.py:143`) |

### B3. LabelFrame-секции

| Секция | Текст | padding |
|---|---|---|
| ВЫБОР ДАТЫ | `📅 ВЫБОР ДАТЫ` | `SPACING.xs` (=4) |
| СОТРУДНИКИ | `👤 СОТРУДНИКИ` | `SPACING.xs` |
| СБОРКА | `🚀 СБОРКА` | `SPACING.xs` |
| ЗА ПЕРИОД | `📆 ЗА ПЕРИОД` | `0` (collapsible) |
| ТЕМА | `🎨 ТЕМА` | `SPACING.xs` |

| Поле | Значение |
|---|---|
| **Расположение** | `content`, `pack(fill=X, pady=_section_gap)` где `_section_gap = (0, SPACING.sm)` (=8) |
| **Цвета** | стиль `TLabelframe`: bg=`bg_sidebar`, border=`border_subtle`, borderwidth=1. Заголовок: `TLabelframe.Label`, fg=`text_muted`, шрифт=`heading` |
| **Зависимости** | обновляется через ttk при `set_theme` |

### B4. DateEntry (`tkcalendar.DateEntry`) — 3 шт

| Поле | date_entry | month_start_entry / month_end_entry |
|---|---|---|
| **Назначение** | Дата сборки за день | Диапазон «С…По» (период) |
| **Расположение** | `date_row` (LEFT, fill=X, expand) | `dates_row` внутри `_per_panel` (collapsible) |
| **width** | 12 | 7 |
| **Цвета** | `background=primary` (L:`#1b4b8a` / D:`#5b8def`), `foreground=text_inverse` (L:`#fff` / D:`#111418`), `headersbackground=primary`, `selectbackground=primary`, `borderwidth=2` |
| **Формат** | `dd.mm.yyyy`, `locale="ru_RU"` | то же |
| **Событие** | `<<DateEntrySelected>>` → `_date_debouncer` (250мс debounce) → `controller.refresh_status`. У period: `_validate_period_range` |
| **Tooltip** | `_date_tooltip` (на date_entry) — показывает день недели динамически (`_weekday_tooltip_text`) |
| **Период-валидация** | если end < start: `foreground → danger` (L:`#c0492f` / D:`#ec6a5f`), добавляется warning-tooltip, кнопки периода `DISABLED`. `ui_sidebar.py:498-558` |
| **Defaults (period)** | start = `today.replace(day=1)` (или пред. месяц если сегодня 1-е), end = `today`. `get_default_period_range` (`ui_sidebar.py:25`) |
| **Зависимости** | `refresh_theme()` перетематизирует все 3 entry вручную (tkcalendar не следует ttk-стилям). `ui_sidebar.py:560-591` |

### B5. Кнопки Sidebar — полный реестр

> Все кнопки: `pack(fill=X, pady=_btn_gap)`, где `_btn_gap = (0, SPACING.xs)` (=4). Стиль по умолчанию `TButton`, если не указан `Action.TButton` / `Ghost.TButton`.

| # | Кнопка | Текст | Стиль | Command | Hotkey | Tooltip |
|---|---|---|---|---|---|---|
| 1 | `refresh_btn` | `🔄` (width=3) | TButton | `refresh_status` | F5 | «Обновить статус» |
| 2 | `add_employee_btn` | `➕ Добавить` | TButton | `add_employee_dialog` | — | — |
| 3 | `attach_btn` | `📎 Привязать` | TButton | `attach_file_dialog` | — | — |
| 4 | `consolidate_btn` | `⚡ СОБРАТЬ ДЕНЬ` | **Action.TButton** | `run_consolidation` | Ctrl+D | «Собрать отчёт за выбранную дату (Ctrl+D)» |
| 5 | `consolidate_all_btn` | `🌍 СОБРАТЬ ВСЕ ДАТЫ` | TButton | `run_consolidation_all_dates` | Ctrl+Shift+D | «…по всем датам сразу (Ctrl+Shift+D)» |
| 6 | `rsch_btn` | `🧾 СОБРАТЬ РСЧ` | TButton | `run_rsch_report` | Ctrl+R | «Сформировать РСЧ-отчёт (Ctrl+R)» |
| 7 | `reconciliation_btn` | `✅ СВЕРИТЬ С РСЧ` | TButton | `run_reconciliation_report` | Ctrl+E | «Сверить… (Ctrl+E)» |
| 8 | `auto_reconciliation_btn` | `✅ АВТОСВЕРКА` | **Action.TButton** | `run_auto_reconciliation_day` | — | — |
| 9 | `consolidate_month_btn` | `📊 СОБРАТЬ ПЕРИОД` | **Action.TButton** | `run_consolidation_month` | Ctrl+M | «…за период С…По (Ctrl+M)» |
| 10 | `rsch_month_btn` | `🧾 СОБРАТЬ РСЧ ЗА ПЕРИОД` | TButton | `run_rsch_report_month` | Ctrl+Shift+R | «…за период (Ctrl+Shift+R)» |
| 11 | `settings_btn` | `⚙ НАСТРОЙКИ` | TButton | `_open_settings_fallback` | — | «Открыть диалог настроек…» |
| 12 | `shortcuts_btn` | `⌨ ГОРЯЧИЕ КЛАВИШИ` | TButton | `_open_shortcuts` | F1 | «Показать сочетания клавиш (F1)» |
| 13 | `_per_toggle` | `▶  Развернуть` / `▼  Свернуть` | **Ghost.TButton** | `_toggle_period_section` | — | — |
| — | preset: «Этот месяц» / «Пред. месяц» | TButton | `_set_current_month` / `_set_previous_month` | — | — |

**Глобальная блокировка:** `apply(snap)` (`ui_sidebar.py:740-758`) — пока идёт любая операция (`snap.current != ""`), все 10 operation-кнопок переходят в `state(["disabled"])`. Список `_OPERATION_BUTTONS_ATTRS` (`ui_sidebar.py:727-738`).

**Цвета кнопок (state matrix):**

| Стиль | normal bg/fg | active (hover/press) | disabled |
|---|---|---|---|
| TButton | `bg_panel` / `text` | bg→`primary`, fg→`text_inverse` | bg→`bg_panel`, fg→`text_muted` |
| Action.TButton | `primary` / `text_inverse` | bg→`primary_active` (L:`#163d70` / D:`#7aa2f7`) | bg→`bg_panel`, fg→`text_muted` |
| Ghost.TButton | `bg_main` / `text` | bg→`bg_panel`, fg→`primary` (link-like) | bg→`bg_main`, fg→`text_muted` |

Шрифт всех: `button` (`("Segoe UI Semibold", 10)`). Padding: `(button_pad_x=12, button_pad_y=6)` × density-factor. relief=flat, borderwidth=0.

### B6. Combobox кураторов (`ttk.Combobox`)

| Поле | Значение |
|---|---|
| **Назначение** | Выбор куратора для сборки |
| **Расположение** | `action_frame`, `pack(fill=X, pady=_btn_gap)` |
| **state** | `readonly` |
| **Значения** | `["Общий отчет", "Куратор Борис", "Куратор Иван"]` |
| **Цвета** | `TCombobox`: fieldbackground=`bg_sidebar`, foreground=`text`, arrowcolor=`text_muted`, border=`border_default`. На focus: bordercolor→`primary`. На readonly: fieldbackground=`bg_sidebar`. На active: arrowcolor→`primary` |
| **Шрифт** | `body` |
| **Padding** | `(SPACING.xs, 4×scale)` |
| **Маппинг** | `get_curator()`: «Общий» → `None`, «Куратор Борис» → `"boris"`, «Куратор Иван» → `"ivan"` (`ui_sidebar.py:687-693`) |

### B7. Radiobutton темы (`ttk.Radiobutton` × 3)

| Поле | Значение |
|---|---|
| **Назначение** | Переключатель темы light/dark/system |
| **Расположение** | `theme_row` (Sidebar.TFrame), каждый `pack(side=LEFT, padx=(0, SPACING.xs))` |
| **Значения** | `("light", "☀️ Светлая")`, `("dark", "🌙 Тёмная")`, `("system", "💻 Системная")` |
| **Цвета** | `TRadiobutton`: bg=`bg_sidebar`, fg=`text`. На active: bg=`bg_sidebar`. На disabled: fg=`text_muted` |
| **Шрифт** | `body` |
| **Command** | `_on_theme_changed` → `controller.set_theme(value)` |
| **System-режим** | при `"system"` запускается `_poll_system_theme` (каждые 5с) — следует за ОС |

### B8. StatsPanel (`ttk.LabelFrame`)

> Источник: `APP/core/ui/ui_stats_panel.py`.

| Поле | Значение |
|---|---|
| **Назначение** | Две прогресс-полосы: готовность сотрудников (верх) и текущая операция (низ) |
| **Расположение** | `sidebar.content`, `pack(fill=X, pady=(SPACING.sm, 0))`. Скроллится вместе с настройками |
| **Текст** | `📈 СТАТИСТИКА ДНЯ` |
| **Padding** | `SPACING.sm` (=8) |
| **stats_label** | 3 строки: «Готово: r/t», «Приход: X / Расход: Y» (если есть), «Ошибки: N». Стиль `Sidebar.TLabel`, `wraplength=280`, `justify=LEFT` |
| **readiness_bar** | `ttk.Progressbar`, `variable=readiness_var`, `maximum=100`, `pack(fill=X)`. Caption «Готовность сотрудников:», `pady=(10, 0)` |
| **operation_bar** | `ttk.Progressbar`, `variable=operation_var`, `maximum=100`, `pack(fill=X, pady=(2, 0))`. Caption «Текущая операция:», `pady=(8, 0)` |
| **Цвета (Progressbar)** | trough=`bg_panel`, bar=`primary`, border=`border_subtle`. `thickness=progress_h` (=12) |
| **API** | `set_readiness(v)` / `set_operation(v)` clamp [0, 100]. `update_stats(ready, total, income, expense, errors)` |
| **Зависимости** | ttk стили обновляются автоматически при `set_theme` |

---

## Часть C. Главная область (Notebook + вкладки)

> Источник: `APP/core/ui/ui_dashboard.py`.

### C1. Notebook (`ttk.Notebook`)

| Поле | Значение |
|---|---|
| **Назначение** | Контейнер вкладок главной области |
| **Расположение** | `main_area`, `pack(fill=BOTH, expand=True)` |
| **Стиль** | `TNotebook`: bg=`bg_main`, borderwidth=0, tabmargins=(0,4,0,0). Bordercolor/lightcolor/darkcolor все = `bg_main` (чтобы не было белой рамки в dark) |
| **Tab** | `TNotebook.Tab`: bg=`bg_main`, fg=`text_muted` → **selected**: bg=`bg_sidebar`, fg=`primary` → **active (hover)**: bg=`bg_panel`, fg=`text`. Padding `(tab_pad_x=16, tab_pad_y=10)` × density |
| **Шрифт tab** | `body` |
| **Порядок вкладок** | Сотрудники (выбрана по умолчанию) → Панель → Отчёты → 📜 История → Диагностика → Логи → 🔗 Алиасы сверки |
| **tab-frame** | каждый `ttk.Frame(notebook, padding=SPACING.md=12, style="Main.TFrame")` |

### C2. Вкладка «Сотрудники» — `EmployeeTable`

> Источник: `APP/core/ui/ui_employee_table.py`.

| Поле | Значение |
|---|---|
| **Назначение** | Таблица готовности отчётов сотрудников с поиском, фильтром, сортировкой, контекстным меню, drag-and-drop |
| **Расположение** | `employees_tab`, `pack(fill=BOTH, expand=True)` |
| **Цвета** | Main.TFrame bg=`bg_main` |

**Header (`header_frame`):**
- Заголовок: «📋 СТАТУС ГОТОВНОСТИ ОТЧЕТОВ», стиль `Header.TLabel` (display font, primary).
- Кнопки (btn_frame, справа): «📂 Папка Master» → `open_master_folder`; «📋 Должники» → `copy_missing_to_clipboard`. padx=`SPACING.xs`.

**Search-row (`search_frame`):**
- `ttk.Entry` (LEFT, fill=X, expand), `textvariable=search_var`, trace→`_search_debouncer` (300мс) → `filter_tree`.
- Combobox-фильтр (RIGHT, width=12, `state=readonly`): `["Все", "Готово", "Нет файла", "Должники"]`. Событие `<<ComboboxSelected>>` → `_on_status_filter_change`.

**Treeview (`tree`):**

| Свойство | Значение |
|---|---|
| columns | `("Employee", "Status", "Path")` |
| show | `headings` |
| selectmode | `extended` (multi-select для batch-операций, UX-015) |
| Стиль | `Treeview` (по умолчанию) |
| rowheight | `row_h_compact` (=26) при compact density, иначе `row_h` (=32) |
| Заголовки | «Сотрудник ▲▼», «Статус ▲▼», «Файл отчета ▲▼» — кликабельны, toggle asc/desc (UX-012) |
| Колонки (weights) | Employee=35%, Status=20%, Path=45% от ширины минус 20px scrollbar. minwidth=60. `_resize_columns` на `<Configure>` |
| bg/fieldbackground | `bg_sidebar`; foreground=`text`; border=`border_subtle` |
| Heading-стиль | body_bold, bg=`bg_panel`, fg=`text_muted`, padding=`(SPACING.sm, 6×scale)`. На active: bg→`border_default`, fg→`text` |

**Теги строк (`_configure_tags`):**

| Тег | Семантика | foreground | background (8% tint) | font |
|---|---|---|---|---|
| `odd` | нечётная строка | — | `bg_panel` | — |
| `even` | чётная строка | — | `bg_sidebar` | — |
| `hover` | под курсором | — | `border_subtle` | — |
| `ready` | готов | `success` (L:`#1a8a4e`/D:`#5fb87a`) | blend(bg_sidebar, success, 0.08) | body_bold |
| `missing` | нет файла | `danger` (L:`#c0492f`/D:`#ec6a5f`) | blend(bg_sidebar, danger, 0.08) | body_bold |
| `partial` | нет данных | `warning` (L:`#b45309`/D:`#e0a341`) | blend(bg_sidebar, warning, 0.08) | body_bold |
| `empty_state` | placeholder | `text_secondary` | — | — |

> Теги аддитивны: `insert_row` сливает `odd`/`even` со статусным тегом.

**Selection state** (из `style.map Treeview`): selected → bg=`primary`, fg=`text_inverse`.

**События:**

| Событие | Обработчик |
|---|---|
| `<Motion>` | `_on_tree_motion` — добавляет тег `hover` на строку под курсором |
| `<Leave>` | `_on_tree_leave` — снимает тег `hover` |
| `<Button-3>` | `_show_context_menu` — selection_set + `menu.post` |
| `<Double-1>` | `controller.open_employee_file` |
| `<Configure>` (tree_frame) | `_resize_columns` |
| `<<Drop>>` (если tkinterdnd2 доступен) | `_on_file_drop` — attach .xlsx к сотруднику под курсором |

**Контекстное меню (`tk.Menu`):**

| Поле | Значение |
|---|---|
| tearoff | 0 |
| bg / fg | `bg_sidebar` / `text` |
| activebg / activefg | `primary` / `text_inverse` |
| borderwidth | 0 |
| Пункты | `📁 Открыть папку` → `open_employee_folder`; `📊 Открыть файл` → `open_employee_file`; separator; `❌ Удалить сотрудника` → `delete_employee` (batch по selection) |
| Зависимости | `ThemeManager.register_menu(menu)` — tk.Menu не следует ttk, перетематизируется через реестр `_themed_menus` |

### C3. Вкладка «Панель» — Home

| Поле | Значение |
|---|---|
| **Назначение** | Сводка состояния + быстрые действия + последние результаты |
| **Расположение** | `home_tab` (Main.TFrame, padding=SPACING.md) |

**LabelFrame «Состояние»** (Main.TLabelframe, padding=SPACING.sm): `state_label` (justify=LEFT, wraplength=адаптивно через `<Configure>`, clamp [200, 1200]).

**LabelFrame «Быстрые действия»**: 4 кнопки TButton в ряд (padx=SPACING.sm между ними): «Открыть последний Master» / «Открыть последнюю сверку» / «Открыть backup» / «Открыть логи».

**LabelFrame «Последние результаты»** (fill=BOTH, expand): `results_tree`.

`results_tree` (Treeview):

| Колонка | Заголовок | width | anchor | stretch |
|---|---|---|---|---|
| type | Тип | 120 | W | нет |
| status | Статус | 90 | W | нет |
| time | Время | 140 | W | нет |
| path | Путь | 260 | W | нет |
| message | Сообщение | 360 | W | да |

Теги: `empty` (fg=`text_muted`), `success` (fg=`success`, bg=8% tint, body_bold), `error` (fg=`danger`, bg=8% tint, body_bold). Hover через `attach_treeview_hover`. Событие `<Double-1>` → `_open_selected_result`. Empty-state на старте: `("Нет данных", "", "", "", "Запустите сборку отчета")`.

### C4. Вкладка «Отчёты» — `reports_tree`

| Поле | Значение |
|---|---|
| **Назначение** | Дерево найденных отчётных файлов с путями, размерами, mtime |
| **Стиль** | **`Mono.Treeview`** (tabular-figures для путей/размеров) |
| Панель действий | «Обновить», «Открыть», «Открыть папку», «Backup» (padx=SPACING.sm) |

Колонки:

| Колонка | Заголовок | width | stretch |
|---|---|---|---|
| name | Файл | 160 | нет |
| status | Статус | 90 | нет |
| mtime | Изменен | 130 | нет |
| size | Размер | 80 | нет |
| path | Путь | 520 | да |

Событие `<Double-1>` → `_open_selected_report`. Hover через `attach_treeview_hover`. Состояния: «✅ найден» / «⚠️ не найден».

### C5. Вкладка «📜 История» — `history_tree`

| Поле | Значение |
|---|---|
| **Назначение** | Последние операции из БД (до 50 сессий) |
| Панель действий | «🔄 Обновить», подпись «Последние операции (из БД):» |

Колонки: Date(140) / Type(120) / Status(100) / Files(60) / Target(100, **stretch=True**).

Теги статусов (только foreground):

| Тег | fg |
|---|---|
| `completed` | `success` |
| `failed` | `danger` |
| `cancelled` | `warning` |

Типы: «Сборка за день» / «Сборка все даты» / «Сборка за период» / «РСЧ» / «РСЧ за период» / «Сверка». Empty-state тег `empty`. Hover через `attach_treeview_hover`. Загружается на init (best-effort).

### C6. Вкладка «Диагностика» — `diagnostics_tree`

| Поле | Значение |
|---|---|
| **Назначение** | Результаты лёгкой диагностики системы |
| Панель действий | «Проверить систему» (**Action.TButton**) → `run_diagnostics`; «Скопировать диагностику» → `copy_diagnostics` |
| Стиль | **`Mono.Treeview`** |

Колонки: check(170) / status(90) / detail(260, stretch) / path(520, stretch). Hover через `attach_treeview_hover`.

### C7. Вкладка «Логи» — `tk.Text`

| Поле | Значение |
|---|---|
| **Назначение** | Read-only просмотр последних событий логов (до 150 строк) |
| Источники | `APP/startup_log.txt`, `repo/gui_error_log.txt` (`read_recent_logs`, limit=150) |
| Панель действий | «Обновить», «Открыть лог работы (Python)», «Открыть лог запуска (Батник)», «Открыть gui_error_log.txt», «Открыть папку логов» |
| Виджет | `tk.Text` (НЕ ttk) — `state="disabled"`, `wrap=WORD` |
| Цвета | bg=`bg_panel` (recessed), fg=`text`, insertbackground=`text`, selectbackground=`primary`, selectforeground=`text_inverse`, highlightthickness=0, borderwidth=0 |
| Scrollbar | vertical (RIGHT, fill=Y) + horizontal (BOTTOM, fill=X) |
| Зависимости | `ThemeManager.register(text, bg_key="bg_panel", fg_key="text")` (`ui_dashboard.py:392`) |
| Refresh | `_refresh_logs`: state→normal, delete, insert, see(END), state→disabled |

### C8. Вкладка «🔗 Алиасы сверки» — `AliasesTab`

> Источник: `APP/core/ui/ui_aliases.py`.

| Поле | Значение |
|---|---|
| **Назначение** | Управление соответствиями заказчиков куратор↔РСЧ для сверки |
| **Расположение** | `aliases_tab` (Main.TFrame) |

**Header:** «🔗 Соответствия заказчиков для сверки» (`Header.TLabel`) + подпись (`Muted.TLabel`, padx=12).

**Toolbar (4 кнопки + hint справа):**
- «➕ Добавить» → `_on_add` (padx=SPACING.xs)
- «✏️ Изменить» → `_on_edit`
- «🗑️ Удалить» → `_on_delete`
- «🔄 Обновить» → `refresh`
- hint «Двойной клик по строке — изменить» (Muted.TLabel, справа)

**Treeview (`tree`)**, selectmode=`browse`:

| Колонка | Заголовок | width | stretch |
|---|---|---|---|
| id | ID | 50 | нет |
| master | Заказчик (куратор) | 300 | да |
| rsch | Заказчик (РСЧ) | 300 | да |
| notes | Заметки | 200 | да |
| updated | Обновлено | 140 | нет |

Grid-layout с vertical + horizontal scrollbar. Событие `<Double-1>` → `_on_edit`.

**Footer-hint:** пояснение про «Сверено = точное совпадение суммы + исполнителя + заказчика (или алиаса)», Muted.TLabel, wraplength=900.

**Диалог add/edit** (`tk.Toplevel`, 780×280, minsize 640×240, transient+grab_set, bg=`bg_main`):
- 2 `ttk.Entry` (Заказчик куратора / Заказчик РСЧ), `tk.Text` height=3 для заметок.
- Кнопки «Сохранить» / «Отмена».
- Контекстное меню на entries: Вырезать/Копировать/Вставить/Выделить всё (через `event_generate`).
- Горячие клавиши: Enter→save, Escape→destroy.
- `notes_entry` зарегистрирован: `register(text, bg_key="bg_sidebar", fg_key="text")` (`ui_aliases.py:202`).
- Ошибки сохранения идут через `error_presenter.present_error` (без сырого `str(e)` в UI), кроме `ValueError` (бизнес-валидация — оставлен на messagebox).

---

## Часть D. Попапы и диалоги

### D1. Toast (`ToastManager` / `ToastLevel`)

> Источник: `APP/core/ui/toast.py`. Заменяет blocking `messagebox.showinfo/showerror` для некритичных уведомлений.

| Поле | Значение |
|---|---|
| **Назначение** | Стек некритичных уведомлений в правом нижнем углу |
| **Контейнер** | `tk.Toplevel(root)` + `wm_overrideredirect(True)` (borderless) |
| **max_stack** | 3 (новый вытесняет самый старый через `_dismiss(early=True)`) |
| **Якорение** | `_repack`: `root_x + root_w - w - 20`, `root_y + root_h - h - offset`. margin=20, gap между тостами=8. Новейший — снизу |

**4 уровня (ToastLevel):**

| Уровень | Иконка | bg_key | fg_key | L:bg | D:bg |
|---|---|---|---|---|---|
| INFO | `ℹ` | `info` | `text_inverse` | `#0e6e8c` | `#4db0c9` |
| SUCCESS | `✓` | `success` | `text_inverse` | `#1a8a4e` | `#5fb87a` |
| WARNING | `⚠` | `warning` | `text_inverse` | `#b45309` | `#e0a341` |
| ERROR | `✕` | `danger` | `text_inverse` | `#c0492f` | `#ec6a5f` |

> WARNING использует `text_inverse` (НЕ `text`) для контраста в обеих темах (UX-020).

**Структура содержимого:**
- `inner = make_popup_frame(toplevel, bg, pad_x=16, pad_y=10)` — 1px themed border (`highlightthickness=1`, `highlightbackground=popup_border_color()`).
- title_label: `"{icon}  {title}"`, font=`body_bold`, anchor=W.
- msg_label (если message): font=`caption`, wraplength=360, justify=LEFT, pady=(2,0).
- detail-секция (FIX-006, если `detail` непустой): toggle-линк «Подробнее ▼» / «Скрыть ▲» (font=`micro + underline`, cursor=`hand2`), разворачивает detail_frame (bg=`_darken(bg, 0.94)`, padx=8, pady=6, font=`micro`, wraplength=340).
- close_label «×» (font=body_bold+1, place relx=1.0, x=-8, y=4, anchor=ne). Hover: bg→`_darken(bg, 0.88)`.

**Анимация (из `ANIMATION`):**

| Параметр | Значение | Эффект |
|---|---|---|
| fade_delay_ms | 16мс | интервал кадра |
| toast_fade_in_steps | 8 (≈128мс) | alpha 0→1 |
| toast_fade_out_steps | 10 (≈160мс) | alpha 1→0 |
| toast_slide_px | 30px | slide-in справа во время fade-in |

При неподдержке alpha (часть X11) — fade пропускается, slide-in остаётся. Начальная позиция `+-10000+-10000` (off-screen) против flash.

**События:**
- `auto_after_id`: авто-dismiss через `duration_ms` (по умолчанию 4000; error=6000).
- `<Button-1>` на close_label → `_dismiss`.
- `<Button-1>` на toggle_label → `_toggle_detail`.
- `<Destroy>` на root → `_cleanup_all` (отменяет все pending timers).

**API:** `show(level, title, message, duration_ms=4000, detail="")` · удобные: `info/success/warning/error(title, message=, *, detail=, **kwargs)`.

### D2. Tooltip (`Tooltip`)

> Источник: `APP/core/ui/tooltip.py`.

| Поле | Значение |
|---|---|
| **Назначение** | Маленький popup рядом с курсором при hover |
| **Контейнер** | `tk.Toplevel(widget)` + `wm_overrideredirect(True)` |
| **Цвета** | bg=`tooltip_bg` (L:`#1a2332` / D:`#0c0e12`), fg=`tooltip_fg` (L:`#f5f6f8` / D:`#e7ebf3`). Инверсный тёмный popup в обеих темах. Emergency-fallback hex: `#0c0e12` / `#e7ebf3` |
| **Шрифт** | `caption` (`("Segoe UI", 9)`) |
| **wraplength** | 280 |
| **offset** | `+12/+12` от курсора (`_DEFAULT_OFFSET_PX=12`) |
| **delay** | 300мс (UX-011, уменьшено с 400) |
| **Структура** | `make_popup_frame(tip, bg, pad_x=8, pad_y=6)` — тот же 1px border, что у toast. Label с `text=_resolved_text()` |
| **Fade-in** | `_FADE_STEPS=6` (≈96мс), alpha 0→1 |
| **Fade-out** | НЕТ — мгновенный disappear на `<Leave>` (ощущается быстрее) |

**text** может быть `str` ИЛИ `callable[[], str]` (динамический текст — например, день недели в Sidebar).

**События (bind на widget, `add="+"`):**

| Событие | Обработчик |
|---|---|
| `<Enter>` | `_on_enter` — запуск `after(delay_ms, _show)` |
| `<Leave>` | `_on_leave` — cancel + `_hide` |
| `<Motion>` | `_on_motion` — двигает popup за курсором |
| `<ButtonPress>` | `_on_leave` (прячем при клике) |
| `<Destroy>` | `_on_destroy` — cleanup timers |

**API:** `Tooltip(widget, text_or_callable, delay_ms=300)` · `set_text(str)` обновляет видимый popup.

### D3. Welcome-dialog (`WelcomeDialog`)

> Источник: `APP/core/ui/welcome_dialog.py`. Показывается один раз на fresh install.

| Поле | Значение |
|---|---|
| **Назначение** | 3-шаговый онбординг-чеклист |
| **Контейнер** | `tk.Toplevel(parent)` (НЕ messagebox), `transient`, `resizable(False, False)`, `grab_set`, `focus_set` |
| **Title** | «Добро пожаловать в Master-Report» |
| **Цвета** | bg=`bg_main` (themed) |
| **Флаг-файл** | `APP/first_run.json` `{"first_run_done": bool}`. Отдельно от `runtime_state.json` |
| **Header** | «👋 Добро пожаловать в Master-Report» (`Header.TLabel`), подпись (`Muted.TLabel`). Padding `(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.md)` |
| **Separator** | `ttk.Separator`, padx=`SPACING.lg` |
| **Body** | 3 Label (`Main.TLabel`, wraplength=420, pady=`SPACING.xs` между шагами) |
| **Steps** | 1. Добавьте сотрудников → 2. Выберите дату → 3. Нажмите Сборка → Собрать день (Ctrl+D) |
| **Action** | «Начать работу» (`Action.TButton`, pack side=RIGHT). Padding `(SPACING.lg, SPACING.sm, SPACING.lg, SPACING.lg)` |
| **Горячие клавиши** | `<Return>` / `<Escape>` → `_on_start` |
| **Центрирование** | геометрия `+{px+(pw-w)//2}+{py+(ph-h)//2}` над parent |
| **WM_DELETE_WINDOW** | = `_on_start` (флаг пишется даже при закрытии крестом) |
| **Guard** | `_display_available()` — пропускает headless/CI. `show_welcome_if_first_run` проглатывает все ошибки (онбординг НИКОГДА не ломает startup) |

### D4. Shortcuts-dialog (`ShortcutsDialog`)

> Источник: `APP/core/ui/shortcuts_dialog.py`. F1 или кнопка в Sidebar.

| Поле | Значение |
|---|---|
| **Назначение** | Референс горячих клавиш (8 пар) |
| **Контейнер** | `tk.Toplevel`, `transient`, `resizable(False, False)`, `grab_set` |
| **Title** | «Горячие клавиши» |
| **Цвета** | bg=`bg_main` |
| **Header** | «⌨ Горячие клавиши» (`Header.TLabel`) + подпись `Muted.TLabel` |
| **Body** | grid 2 колонки: column 0 (weight=0) — combo шрифтом `mono`, padx=`SPACING.md`; column 1 (weight=1) — action, wraplength=360 |

**8 пар** (синхронизировано с `_bind_shortcuts`, держать в sync вручную):

| Комбо | Действие |
|---|---|
| Ctrl+D | Собрать отчёт за день |
| Ctrl+Shift+D | Собрать по всем датам |
| Ctrl+M | Собрать за период |
| Ctrl+R | Сформировать РСЧ за день |
| Ctrl+Shift+R | Сформировать РСЧ за период |
| Ctrl+E | Сверка данных |
| F5 | Обновить статус |
| Escape | Отменить операцию |

Action: «Закрыть» (`Action.TButton`). `<Return>` / `<Escape>` → close. Guard как у Welcome.

### D5. SettingsDialog (`tk.Toplevel`, 8 вкладок)

> Источник: `APP/core/ui/ui_settings.py`. Редактирует **deep-copy** конфига, ничего не пишет на диск до Apply/OK.

| Поле | Значение |
|---|---|
| **Назначение** | Модальный диалог настроек (UI + бизнес-конфиг) |
| **Контейнер** | `tk.Toplevel(parent)`, `transient`, `grab_set`, `resizable(True, True)`, bg=`bg_main`, minsize `600×400` |
| **Title** | «Настройки» |
| **Девиз** | Cancel восстанавливает live-preview (theme/scale/density) из snapshot |
| **Notebook** | `pack(fill=BOTH, expand=True, padx=8, pady=8)` |

**8 вкладок:**

| Вкладка | Содержимое |
|---|---|
| 🎨 Внешний вид | Radiobutton темы (light/dark/system), scale_mode (auto/manual), Spinbox user_scale (0.80–1.50, шаг 0.05) с live-preview, 4 preset-кнопки (0.85/1.0/1.15/1.30), density (compact/normal/comfortable), sidebar_width Spinbox, диагностика (DPI/screen/window/scale/mode, fg=`text_muted`) |
| 📁 Пути и файлы | scrollable. _PathRow × N (Master-файл, source_roots через _ListEditor, archive_dir, output_root, вывод Boris/Ivan, РСЧ last_output_dir), Radiobutton режима РСЧ (combined/separate) |
| ⚡ Производительность | Spinbox max_workers (0–64), Checkbutton isolate_calamine |
| 🌐 Сеть | scrollable. _ListEditor drive_letters (default `[Q, Z]`) |
| 🧮 Логика | scrollable. Checkbutton commission_is_percent, _ListEditor income_overrides, _ListEditor return_keywords |
| 🗄 База данных | Entry path, Spinbox timeout (1–120), Checkbutton use_wal |
| 💾 Бэкапы | Spinbox excel_keep (1–100) |
| ℹ О программе | info-таблица (Версия/config.yaml/employees.yaml/Тема/Масштаб/Плотность), External-редакторы (config.yaml/employees.yaml в Блокноте), кнопка «↺ Сбросить настройки интерфейса» |

**Live-preview:** `_preview_appearance` вызывает `ThemeManager.apply_preferences` + `set_theme(resolve_effective(theme_var))`. Срабатывает на любой change: theme, scale_mode, user_scale (trace_add), density, preset-клик.

**Action-buttons** (btn_frame, padx=8, pady=(0,8)): «OK» (RIGHT), «Отмена» (RIGHT), «Применить» (RIGHT), «↺ Сброс» (LEFT, с messagebox.askyesno-подтверждением).

**Центрирование** над parent: `+{px+(pw-dw)//2}+{py+(ph-dh)//2}`.

**Apply (`_apply`):** сохраняет UI-prefs (`_collect_prefs` → `store.save_preferences` → `gui.apply_ui_preferences`), собирает бизнес-конфиг из виджетов в `_work`, writeback в `ConfigController`, показывает toast-сводку изменений (`_compute_prefs_diff`, до 5 пунктов).

**Хелперы:**
- `_PathRow` — Label + Entry (fill=X, expand) + «…» button (width=3). path_type: `dir` / `file` / `save_dir` / `save_file`.
- `_ListEditor` — `tk.Listbox` (height=6) с Add/Edit/Delete. Listbox themed: `register(listbox, bg_key="bg_sidebar", fg_key="text")`, selectbackground=`primary`, selectforeground=`text_inverse`.
- `_scrollable` — Canvas + Scrollbar wrapper для длинных вкладок (Paths/Network/Logic). Canvas registered: `register(canvas, bg_key="bg_sidebar", fg_key=None)`. Mousewheel через `bind_all` на `<Enter>`/`<Leave>` canvas.

### D6. messagebox.askyesno (диалоги подтверждения)

> Не-themed (нативный Tk), используется где нужен бинарный выбор пользователя.

| Где | Текст | Действие «Да» |
|---|---|---|
| `gui_master.py:384` | «Консолидация завершена. Открыть файл?» | `open_path(path)` — открыть Master |
| `gui_commands/_base.py:128` | обобщённый `ask_open_text` (после любой операции) | `open_path(path)` |
| `gui_commands/_consolidation.py:31,49,73` | предупреждения перед запуском | продолжить операцию |
| `gui_commands/_employee.py:222` | «Удалить [сотрудника]?» | удалить сотрудника |
| `gui_commands/_rsch.py:139` | использовать сохранённый путь РСЧ | — |
| `ui_aliases.py:154` | «Удалить выбранный алиас?» | `delete_customer_alias` |
| `ui_settings.py:773` | «Сбросить настройки интерфейса к умолчаниям?» | `_reset_ui_defaults` |

### D7. Контекстное меню EmployeeTable (`tk.Menu`)

> См. также C2. Отдельный раздел, т.к. tk.Menu — отдельная подсистема перетематизации.

| Поле | Значение |
|---|---|
| **Назначение** | Правый клик на строке сотрудника |
| **Цвета** | bg=`bg_sidebar`, fg=`text`, activebackground=`primary`, activeforeground=`text_inverse`, borderwidth=0, tearoff=0 |
| **Триггер** | `<Button-3>` на `tree` → `_show_context_menu` (selection_set + menu.post) |
| **Пункты** | `📁 Открыть папку` → `open_employee_folder`; `📊 Открыть файл` → `open_employee_file`; separator; `❌ Удалить сотрудника` → `delete_employee` (batch) |
| **Перетематизация** | `ThemeManager.register_menu(menu)` — добавляет в `_themed_menus`, перенастраивается в `set_theme` (`theme.py:513`). Иначе меню залипает в палитре создания |

---

## Часть E. Дерево ttk-стилей

> Источник: `theme.py:apply_styles` (588–1000). Базовый ttk-theme: `clam`. Все стили пересоздаются в `set_theme` через вызов `apply_styles`.

| # | Стиль | Где определён | Где используется | Ключевые опции (normal) |
|---|---|---|---|---|
| 1 | `TFrame` | theme.py:604 | базовый для всех Frame без явного стиля | bg=`bg_main` |
| 2 | `Main.TFrame` | theme.py:605 | `main_area`, таб-фреймы, header-фреймы в дашборде | bg=`bg_main` |
| 3 | `Sidebar.TFrame` | theme.py:606 | `Sidebar`, `scroll_host`, `content`, `theme_row`, `_per_panel` | bg=`bg_sidebar`, relief=flat |
| 4 | `TLabel` | theme.py:614 | body-текст по умолчанию | bg=`bg_main`, fg=`text`, font=`body` |
| 5 | `Sidebar.TLabel` | theme.py:615 | лейблы внутри sidebar (StatsPanel captions) | bg=`bg_sidebar`, fg=`text`, font=`body` |
| 6 | `Header.TLabel` | theme.py:618 | заголовки секций: «📊 ПАНЕЛЬ», «📋 СТАТУС…», заголовки диалогов | font=`display`, fg=`primary`, bg=`bg_main` |
| 7 | `Main.TLabel` | theme.py:625 | лейблы в главной области | font=`body`, fg=`text`, bg=`bg_main` |
| 8 | `Muted.TLabel` | theme.py:633 | подписи/hints под заголовками | font=`caption`, fg=`text_muted`, bg=`bg_main` |
| 9 | `TButton` | theme.py:645 + map:654 | большинство кнопок | bg=`bg_panel`, fg=`text`, font=`button`, padding=(12,6). map: active→bg=primary,fg=text_inverse; disabled→bg=bg_panel,fg=text_muted |
| 10 | `Action.TButton` | theme.py:660 + map:669 | primary CTA: СОБРАТЬ ДЕНЬ, АВТОСВЕРКА, СОБРАТЬ ПЕРИОД, «Начать работу», «Закрыть», «Проверить систему» | bg=`primary`, fg=`text_inverse`. map: active→bg=primary_active; disabled→bg=bg_panel,fg=text_muted |
| 11 | `Ghost.TButton` | theme.py:728 + map:737 | link-like: `_per_toggle` (Развернуть/Свернуть) | bg=`bg_main`, fg=`text`. map: active→bg=bg_panel,fg=primary |
| 12 | `Danger.TButton` | theme.py:713 + map:722 | (зарезервирован) | bg=`danger`, fg=`text_inverse`. map: active→danger_active |
| 13 | `Success.TButton` ⚰ | theme.py:683 + map:692 | **dead** (нет callers в APP/core) | bg=`success`. Удалить нельзя: `test_operation_status_bar.py` зависит |
| 14 | `Audit.TButton` ⚰ | theme.py:698 + map:707 | **dead** (нет callers) | bg=`info`. Удалить нельзя: см. Success |
| 15 | `TLabelframe` | theme.py:745 | секции в sidebar | bg=`bg_sidebar`, relief=flat, border=1, bordercolor=`border_subtle` |
| 16 | `TLabelframe.Label` | theme.py:752 | заголовки LabelFrame в sidebar | bg=`bg_sidebar`, fg=`text_muted`, font=`heading` |
| 17 | `Main.TLabelframe` | theme.py:760 | LabelFrame в дашборде («Состояние», «Быстрые действия»…) | bg=`bg_main`, relief=flat, border=1, bordercolor=`border_subtle` |
| 18 | `Main.TLabelframe.Label` | theme.py:767 | заголовки main LabelFrame | bg=`bg_main`, fg=`text_muted`, font=`heading` |
| 19 | `Card.TLabelframe` ⚰ | theme.py:773 | **dead** (нет callers) | bg=`bg_sidebar`. Themed, безвреден |
| 20 | `Card.TLabelframe.Label` ⚰ | theme.py:780 | **dead** | bg=`bg_sidebar`, fg=`text_muted`, font=`heading` |
| 21 | `Treeview` | theme.py:788 + map:807 | EmployeeTable, results_tree, history_tree, aliases tree | font=`body`, rowheight=`row_h`/`row_h_compact`, bg/fieldbackground=`bg_sidebar`, fg=`text`. map: selected→bg=primary,fg=text_inverse |
| 22 | `Treeview.Heading` | theme.py:798 + map:816 | заголовки всех Treeview | font=`body_bold`, bg=`bg_panel`, fg=`text_muted`, padding=(sm, 6×scale). map: active→bg=border_default,fg=text |
| 23 | `Mono.Treeview` | theme.py:829 + map:839 | reports_tree, diagnostics_tree (path-heavy) | font=`mono`, rowheight=`row_h`/`row_h_compact`, bg=`bg_sidebar`. map: selected→primary |
| 24 | `TEntry` | theme.py:846 + map:859 | поля ввода (поиск, settings entries) | fieldbackground/bg=`bg_sidebar`, fg=`text`, insertcolor=`primary`, border=`border_default`, selectbackground=`primary`. padding=(xs, 4×scale). map: focus→border=primary |
| 25 | `TCombobox` | theme.py:865 + map:878 | curator combo, status-filter combo | fieldbackground=`bg_sidebar`, fg=`text`, arrowcolor=`text_muted`, border=`border_default`. map: readonly→fieldbackground=bg_sidebar; focus→border=primary; active→arrowcolor=primary |
| 26 | `TScrollbar` (V+H) | theme.py:891 + map:900 | все scrollbar (sidebar, treeview, text, settings canvas) | bg=`border_default`, troughcolor=`bg_main`, arrowcolor=`text_muted`, width=`scrollbar_w` (=10). map: active→bg=text_muted, arrowcolor=text |
| 27 | `TNotebook` | theme.py:911 | главный notebook, settings notebook | bg=`bg_main`, borderwidth=0, tabmargins=(0,4,0,0), bordercolor/lightcolor/darkcolor=`bg_main` |
| 28 | `TNotebook.Tab` | theme.py:921 + map:932 | вкладки | font=`body`, bg=`bg_main`, fg=`text_muted`, padding=(tab_pad_x, tab_pad_y). map: selected→bg=bg_sidebar,fg=primary; active→bg=bg_panel,fg=text |
| 29 | `TCheckbutton` | theme.py:942 + map:945 | settings checkbuttons | bg=`bg_sidebar`, fg=`text`, font=`body`. map: active→bg=bg_sidebar; disabled→fg=text_muted |
| 30 | `TRadiobutton` | theme.py:950 + map:953 | theme-radiobutton, settings radiobuttons | bg=`bg_sidebar`, fg=`text`, font=`body`. map: active→bg=bg_sidebar; disabled→fg=text_muted |
| 31 | `TProgressbar` | theme.py:960 | readiness_bar, operation_bar | thickness=`progress_h` (=12), troughcolor=`bg_panel`, background=`primary`, bordercolor=`border_subtle` |
| 32 | `StatusBar.TFrame` ⚰ | theme.py:971 | **dead** (OperationStatusBar удалён из layout) | bg=`bg_panel`, relief=flat. Класс оставлен ради тестов |
| 33 | `StatusBar.TLabel` ⚰ | theme.py:972 | **dead** | bg=`bg_panel`, fg=`text_muted`, font=`caption` |
| 34 | `TSpinbox` | theme.py:980 + map:993 | settings spinbox (scale, workers, timeout, keep, sidebar_w) | fieldbackground/bg=`bg_sidebar`, fg=`text`, arrowcolor=`text_muted`, border=`border_default`, insertcolor=`primary`, selectbackground=`primary`. map: focus→border=primary; active→arrowcolor=primary |

**Легенда:** ⚰ — мёртвый стиль (нет живых callers в `APP/core`). Удаление заблокировано зависимостями в тестах (`tests/test_operation_status_bar.py`). Подробности — комментарий в `theme.py:675-681`.

**Helpers (не стили, но часть стилевой системы):**

| Функция | Где | Назначение |
|---|---|---|
| `popup_border_color()` | theme.py:1012 | resolve border-цвета для попапов: `border_subtle` → `trough` → `#d8dce4` |
| `make_popup_frame(parent, bg, pad_x, pad_y)` | theme.py:1022 | tk.Frame с 1px themed border (highlightthickness=1). Общий для toast и tooltip |
| `attach_treeview_hover(tree, tag="hover")` | theme.py:1041 | навешивает row-hover на Treeview (тег `hover`, bg=`border_subtle`). Используется дашборд-деревьями |
| `ThemeManager.register(widget, bg_key, fg_key)` | theme.py:242 | реестр tk-виджетов (Canvas, Label, Text, Listbox) для перетематизации |
| `ThemeManager.register_menu(menu, …)` | theme.py:251 | реестр tk.Menu для перетематизации (`_themed_menus`) |
| `ThemeManager.set_theme(name)` | theme.py:476 | переключение палитры: обновляет COLORS, rebuild fonts, `apply_styles`, перетематизирует реестры register/register_menu |
| `ThemeManager.viewport_mode()` | theme.py:375 | классификация ширины: `<900` compact · `900–1400` normal · `>1400` large |

---

## Приложение. Плотность и масштаб — как это меняет пиксели

> Полные правила — в `02_DESIGN_SYSTEM.md` §5, §6. Здесь — артефакты, важные для UI-спецификации.

### Плотность (DENSITY) — множитель для PADDING

| Токен | compact ×0.70 | normal ×1.00 | comfortable ×1.35 |
|---|---|---|---|
| button_pad_x (12) | 8.4 | 12 | 16.2 |
| button_pad_y (6) | 4.2 | 6 | 8.1 |
| tab_pad_x (16) | 11.2 | 16 | 21.6 |
| tab_pad_y (10) | 7 | 10 | 13.5 |

Высоты кнопок (`button_h=30`), строк (`row_h=32`), scrollbars (`scrollbar_w=10`) **НЕ** масштабируются плотностью — только padding.

При compact density: `row_h_compact=26` вместо `row_h=32` (виден в `Treeview`/`Mono.Treeview` rowheight).

### Масштаб (SCALE) — `_scale ∈ [0.72, 2.0]`

Масштабирует **шрифты** (`_rebuild_fonts`), **все SPACING** (`value × _scale × _density_factor`), **CONTROL** (`button_h`, `row_h`, `scrollbar_w`, `progress_h`, `tab_pad_*`…) и некоторые padding-части (`Treeview.Heading` padding=`(sm, 6×scale)`, `TEntry`/`TCombobox` padding=`(xs, 4×scale)`).

Ширина Sidebar пересчитывается на change-scale через `add_scale_listener` → `_recompute_width` (`ui_sidebar.py:423`).

---

## Контрольный список для визуальной регрессии (QA)

| # | Что проверить | Где смотреть |
|---|---|---|
| 1 | Все кнопки одной высоты (30px), padding соответствует density | Sidebar, дашборд |
| 2 | Primary CTA ровно один на экран в idle (Action.TButton) | Sidebar: СОБРАТЬ ДЕНЬ + АВТОСВЕРКА + СОБРАТЬ ПЕРИОД (3 — это нормально, они в разных секциях) |
| 3 | Тег `hover` снимается при выходе курсора из Treeview | EmployeeTable, все дашборд-деревья |
| 4 | При busy все 10 operation-кнопок disabled (apply(snap)) | Sidebar |
| 5 | Toast исчезает за 160мс, slide-in 30px, alpha-fade работает на Windows | правый нижний угол |
| 6 | Tooltip появляется через 300мс, исчезает мгновенно | hover на любой кнопке с tooltip |
| 7 | При inverted period-range: fg=danger, кнопки периода DISABLED | Sidebar ЗА ПЕРИОД |
| 8 | tk.Menu (context, alias) следует теме после переключения | правый клик в EmployeeTable |
| 9 | DateEntry (tkcalendar) следует теме после переключения | Sidebar (refresh_theme) |
| 10 | Dead-стили (Success/Audit/Card/StatusBar) не фигурируют в UI нигде | grep `style=` в APP/core |

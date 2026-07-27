# Дизайн-система Master-Report v5.6

> **Источник истины:** `APP/core/ui/theme.py` (`ThemeManager`). Этот документ — человечески-читаемое отражение кода-токенов. При рассинхроне **код выигрывает**.
> Концепция: **«Тихая касса»** — внутренний инструмент казначейства. Спокойный, точный, проверенный. Доверие через плотность и читаемость, не через цвет.

---

## 1. Палитра (COLORS)

Две спроектированные **независимо** темы (dark — НЕ инверсия light, а отдельная Linear-style лестница поверхностей). Источник: `theme.py:_LIGHT` / `_DARK`.

### Light — «Бумажный canvas»

| Токен | Hex | Контраст с text | Назначение |
|---|---|---|---|
| `primary` | `#1b4b8a` | 8.7:1 на белом | корпоративный navy — единственный хроматический акцент |
| `primary_active` | `#163d70` | 10.5:1 | нажатие primary-кнопки |
| `success` | `#1a8a4e` | 4.4:1 | сдержанный лесной (статус готов) |
| `success_active` | `#15703d` | — | нажатие success-кнопки |
| `danger` | `#c0492f` | 4.96:1 | жжёный кирпич (статус ошибки/нет файла) |
| `danger_active` | `#9d3a26` | — | нажатие danger-кнопки |
| `warning` | `#b45309` | 5.02:1 | янтарь-охра (внимание/нет данных) |
| `info` | `#0e6e8c` | 5.79:1 | глубокий циан (информационные тосты) |
| `accent` | `#1b4b8a` | — | алиас primary |
| `bg_main` | `#f5f6f8` | canvas | холодный «бумажный» фон главного окна |
| `bg_sidebar` | `#ffffff` | карточки | чистый лист для панелей/таблиц |
| `bg_panel` | `#eceef2` | recessed | вогнутые зоны / заголовки таблиц |
| `trough` | `#d8dce4` | — | скролл-желоб / неактивные контролы |
| `text` | `#1a2332` | 14.6:1 на белом | «чернильный» navy-уголь — основной текст |
| `text_secondary` | `#3d4859` | — | вторичный текст |
| `text_muted` | `#6b7588` | 4.6:1 на белом (AA) | подписи / placeholders |
| `text_inverse` | `#ffffff` | — | на primary/danger заливке |
| `border_subtle` | `#e2e5eb` | — | тонкая 1px граница карточек |
| `border_default` | `#c4cad4` | — | видимая граница инпутов / фокус-без-фокуса |
| `tooltip_bg` | `#1a2332` | — | тёмный инверсный попап |
| `tooltip_fg` | `#f5f6f8` | — | текст тултипа |

### Dark — «Premium navy-charcoal» (Linear-style)

Независимая лестница поверхностей с navy-оттенком (НЕ чистый #000 — Linear отвергает true-black как «пиксельный»). Акцент lifts на ~3 стопа светлее, чтобы читаться на чёрном.

| Токен | Hex | Назначение |
|---|---|---|
| `primary` | `#5b8def` | lifted azure (4.5:1 как текст на canvas) |
| `primary_active` | `#7aa2f7` | hover/press |
| `success` | `#5fb87a` | смягчённая зелень (7.2:1 на panel) |
| `danger` | `#ec6a5f` | тёплый коралл (5.65:1) |
| `warning` | `#e0a341` | янтарь lifted |
| `info` | `#4db0c9` | циан на ступень светлее |
| `bg_main` | `#111418` | canvas — глубокий navy-charcoal |
| `bg_sidebar` | `#171b21` | surface-1 — карточки (на ступень выше canvas) |
| `bg_panel` | `#1e232b` | surface-2 — recessed/lifted зоны |
| `trough` | `#2a3038` | surface-3 — скролл-желоб |
| `text` | `#e7ebf3` | светло-серый ink (15.5:1 — НЕ чистый белый) |
| `text_secondary` | `#b8c0cc` | вторичный текст |
| `text_muted` | `#8b94a5` | подписи (6.05:1) |
| `text_inverse` | `#111418` | на светлых акцент-кнопках |
| `border_subtle` | `#232830` | hairline карточек (Linear #23252a-стиль) |
| `border_default` | `#363d48` | видимая граница инпутов |
| `tooltip_bg` | `#0c0e12` | на ступень темнее canvas |
| `tooltip_fg` | `#e7ebf3` | текст тултипа |

### Принципы применения акцента
- **Один** хроматический голос (primary). Применяется СКУПО: primary-CTA, активный таб, focus-ring, selection, текст-ссылка.
- Semantic-цвета (success/danger/warning) — muted, не неон. Финансовый alert читается серьёзно, не панично.
- Зелёный НЕ акцент бренда — он семантически занят «positive/прибыль» в финтеке.

---

## 2. Типографика (FONTS)

Системные Windows-шрифты (empirical-проверено через `tkinter.font.families()` на целевой машине). `_BASE_FONTS` → масштабируется через `_rebuild_fonts` на `_scale`.

| Токен | Семейство | Базовый размер | Вес | Назначение |
|---|---|---|---|---|
| `display` | `Segoe UI Semibold` | 14 | Semibold (family) | заголовки секций (Header.TLabel) |
| `heading` | `Segoe UI Semibold` | 12 | Semibold | заголовки LabelFrame-групп |
| `body` | `Segoe UI` | 10 | Regular | основной текст / ячейки таблиц |
| `body_bold` | `Segoe UI Semibold` | 10 | Semibold | статусные теги (готов/ошибка) |
| `caption` | `Segoe UI` | 9 | Regular | подписи / hints |
| `caption_bold` | `Segoe UI Semibold` | 9 | Semibold | emphasis-подписи |
| `micro` | `Segoe UI` | 8 | Regular | status bar / индикатор сети |
| `mono` | `Cascadia Mono` | 10 | Regular | **суммы и пути** (tabular figures, fallback Consolas) |
| `button` | `Segoe UI Semibold` | 10 | Semibold | все кнопки |

### Принципы
- **Semibold как family** (не `"bold"`-флаг) — Tk иначе рендерит алгоритмическим эмболднением Regular-cut → толстый/дефолтный вид.
- **Cascadia Mono для чисел** — tabular figures (каждая цифра идентичной advance-width) → столбцы сумм выравниваются по десятичной точке. `Cascadia Code` НЕ используется (его programming-ligatures ломают числовое выравнивание). Runtime-fallback на `Consolas` через lazy-probe если Cascadia недоступен.
- **Segoe UI Variable НЕ используется** — не виден Tk-перечислению `font.families()`.

---

## 3. Spacing-шкала (SPACING)

6-ступенчатая шкала, источник `theme.py:_BASE_SPACING`. Масштабируется: `value * _scale * _density_factor`.

| Токен | Базовое значение | Назначение |
|---|---|---|
| `xs` | 4px | минимальный отступ (внутри секций, между кнопкой и tooltip) |
| `sm` | 8px | стандартный вертикальный gap между секциями |
| `md` | 12px | средний отступ |
| `lg` | 16px | padding главного контент-фрейма (`padding="15"` ≈ lg) |
| `xl` | 24px | крупный отступ |
| `xxl` | 32px | секционные разделители |

---

## 4. Контролы-геометрия (CONTROL)

Источник `theme.py:_BASE_CONTROL`. Масштабируется на `_scale`.

| Токен | Базовое | Назначение |
|---|---|---|
| `button_h` | 30px | высота кнопки |
| `button_pad_x` | 12px | горизонтальный padding кнопки (×density) |
| `button_pad_y` | 6px | вертикальный padding кнопки (×density) |
| `row_h` | 32px | высота строки Treeview (normal) |
| `row_h_compact` | 26px | высота строки (compact density) |
| `scrollbar_w` | 10px | ширина полосы прокрутки |
| `entry_h` | 28px | высота поля ввода |
| `tab_pad_x` | 16px | горизонтальный padding вкладки (×density) |
| `tab_pad_y` | 10px | вертикальный padding вкладки (×density) |
| `sidebar_min` | 240px | минимальная ширина сайдбара |
| `sidebar_max` | 380px | максимальная ширина сайдбара |
| `icon` | 16px | размер иконки |
| `progress_h` | 12px | толщина прогресс-бара |
| `statusbar_h` | 24px | высота status-полосы |

---

## 5. Плотность (DENSITY)

3 режима, множитель для padding (НЕ для высот кнопок/строк). Источник `_DENSITY_FACTORS`.

| Режим | Множитель | Эффект |
|---|---|---|
| `compact` | ×0.70 | плотнее padding — больше контента на экран |
| `normal` | ×1.00 | стандарт (по умолчанию) |
| `comfortable` | ×1.35 | просторнее — для презентаций/демо |

Сохраняется в `config.yaml:ui.density`.

---

## 6. Адаптивный масштаб (SCALE)

Единый `_scale ∈ [0.72, 2.0]`, вычисляется из **4 сигналов** (`theme.py:_recompute_scale`):

1. **DPI** — `winfo_fpixels("1i") / 96`, округлённый до 0.25.
2. **Высота экрана** — linear-interp [600, 1440] → [0.78, 1.15].
3. **Ширина окна** — linear-interp [700, 1600] → [0.85, 1.12], **пересчитывается на каждом resize** (debounce 120мс).
4. **Ручной множитель** — `user_scale ∈ [0.80, 1.50]`.

`viewport_mode` (классификация ширины окна): `<900` compact · `900–1400` normal · `>1400` large.

Режим: `auto` (по сигналам) или `manual` (только user_scale). Сохраняется в `config.yaml:ui.{scale_mode, user_scale}`.

---

## 7. Status-row-wash (деривация цветов)

Статусные строки в таблицах (ready/missing/partial) получают лёгкий фон-маркер — **8% blend** семантического цвета с `bg_sidebar` через `_lerp_hex` (`theme.py:113`). Достаточно насыщенно чтобы строка выделялась, но достаточно бледно чтобы odd/even-stripe оставался видим.

| Тег | Семантика | Light-tint (8%) | Dark-tint (8%) |
|---|---|---|---|
| `ready` | готов | blend(#fff, success, 0.08) | blend(#171b21, #5fb87a, 0.08) |
| `missing` | нет файла / ошибка | blend(#fff, danger, 0.08) | blend(#171b21, #ec6a5f, 0.08) |
| `partial` | нет данных | blend(#fff, warning, 0.08) | blend(#171b21, #e0a341, 0.08) |

---

## 8. Физические ограничения платформы (Tkinter/ttk)

Эти ограничения определили дизайн-решения — их важно знать QA:

| Ограничение | Следствие |
|---|---|
| **Нет border-radius** на ttk-виджетах (clam theme) | Глубина только через контраст поверхностей + 1px hairline, НЕ тень/радиус |
| **Нет box-shadow** | Elevation через 4-step surface ladder (Linear-стиль) |
| **Нет CSS-градиентов** на виджетах | Сплошная заливка + `highlightthickness` для границ |
| **Treeview font — на весь виджет** (нет per-column) | `Mono.Treeview` стиль для path-heavy деревьев; нельзя моноширинной сделать одну колонку |
| **tk.Menu / DateEntry НЕ следуют ttk styles** | Отдельный реестр `_themed_menus` + `Sidebar.refresh_theme()` для перетематизации |

---

## 9. Анимации (ANIMATION)

`theme.py:ANIMATION` — общий frame-interval для alpha-fade (чтобы тосты и тултипы чувствовались как одна система).

| Токен | Значение | Назначение |
|---|---|---|
| `fade_delay_ms` | 16ms | базовый интервал кадра alpha-fade |
| `tooltip_fade_steps` | 6 (≈96ms) | transient → быстрое появление |
| `toast_fade_in_steps` | 8 (≈128ms) | notification → мягкое появление |
| `toast_fade_out_steps` | 10 (≈160ms) | soft исчезновение |
| `toast_slide_px` | 30px | subtle right-edge slide-in |
| `bg_anim_steps/delay` | 8 / 16ms | плавная смена фона при переключении темы |

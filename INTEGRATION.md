# Master-Report v5.6 — Интеграция адаптивного интерфейса и универсальной панели настроек

В этом каталоге находятся 5 файлов, которые нужно добавить/заменить в вашем
проекте `Master-Report v5.5`:

| Файл (новый/замена)            | Куда положить в проекте                 | Назначение |
|-------------------------------|------------------------------------------|------------|
| `ui/theme.py`                 | `APP/core/ui/theme.py` (замена)          | Движок адаптивного масштабирования v2 |
| `ui/ui_settings.py`           | `APP/core/ui/ui_settings.py` (новый)     | Универсальный диалог настроек (8 вкладок) |
| `ui/ui_sidebar.py`            | `APP/core/ui/ui_sidebar.py` (замена)     | Кнопка «⚙ Настройки» + адаптивная ширина |
| `ui/gui_master_settings.py`   | `APP/core/ui/gui_master_settings.py` (новый) | Mixin: загрузка/применение prefs, открытие диалога |
| `infra/settings_store.py`     | `APP/core/infra/settings_store.py` (новый)| Хранение секции `ui:` в `config.yaml` |

Все файлы проходят `python3 -m py_compile` без ошибок.

---

## Что даёт каждый компонент

### 1. `theme.py` — адаптивное масштабирование v2

**Старое поведение:** масштаб считался **один раз** при старте из DPI и высоты
экрана; padding кнопок был фиксирован `(4,2)`; ширина сайдбара — 22 % экрана;
пересчёт при изменении размера окна отсутствовал.

**Новое поведение:**
- Масштаб `_scale` ∈ `[0.72, 2.0]` считается из **четырёх** сигналов:
  1. **DPI** — `winfo_fpixels("1i")/96`, округление до 0.25.
  2. **Высота экрана** — 600 px → 0.78, 1440 px → 1.15.
  3. **Размер окна (viewport)** — 700 px → 0.85, 1600 px → 1.12. **Пересчитывается при каждом resize окна** (с debounce 120 мс).
  4. **Пользовательский множитель** — 0.80…1.50 (доступность).
- Из единого `_scale` выводятся **все** токены: шрифты (`FONTS`), отступы
  (`SPACING`), радиусы (`RADIUS`), геометрия контролов (`CONTROL`: высота
  кнопки/строки, ширина скроллбара, ширина сайдбара, размер иконок, …).
- Плотность (`compact/normal/comfortable`) дополнительно масштабирует
  только padding, не трогая шрифты.
- `attach_resize_listener(root)` — подписка на `<Configure>` корня.
- `add_scale_listener(cb)` — любой модуль может подписаться на пересчёт
  масштаба (сайдбар пересчитывает ширину, таблица — колонки).
- Точки разрыва: `viewport_mode()` → `compact` (<900 px) / `normal` /
  `large` (>1400 px).
- **Обратная совместимость:** сохранены все публичные символы
  (`COLORS`, `FONTS`, `SPACING`, `set_theme`, `apply_styles`, `init_scaling`,
  `register`, `animate_background`, `resolve_effective`, `palette`).

### 2. `ui_settings.py` — универсальная панель настроек

Модальный диалог `SettingsDialog` с `ttk.Notebook` из 8 вкладок. **Ничего не
пишется на диск** до нажатия «Применить»/«OK»; «Отмена» откатывает даже
живой предпросмотр темы/масштаба.

| Вкладка | Что настраивается |
|---------|-------------------|
| 🎨 Внешний вид | тема (light/dark/system), режим масштаба (авто/ручной), слайдер множителя ×0.80…×1.50 с **живым предпросмотром**, плотность, ширина сайдбара, диагностика экрана |
| 📁 Пути и файлы | **куда сохраняются отчёты/файлы**: `paths.master_file`, `paths.source_roots` (редактор списка), `paths.archive_dir`, `paths.output_root` (новое), `curators.*.output_path` (по каждому куратору), `rsch.last_output_dir`, `rsch.mode` — у каждого поля кнопка «…» (выбор папки/файла) |
| ⚡ Производительность | `performance.max_workers`, `performance.isolate_calamine` |
| 🌐 Сеть | `network.drive_letters` (редактор списка) |
| 🧮 Логика | `logic.commission_is_percent`, `logic.income_overrides`, `logic.return_keywords` |
| 🗄 База данных | `database.path`, `database.timeout`, `database.use_wal` |
| 💾 Байкапы | `backup.excel_keep` |
| ℹ О программе | версия, пути к config.yaml/employees.yaml, текущий масштаб/тема, сброс UI к умолчаниям |

Все вкладки «Пути и файлы», «Логика», «Сеть» с длинным списком полей
обёрнуты в скроллируемый canvas.

### 3. `ui_sidebar.py` — кнопка настроек + адаптивная ширина

- Внизу сайдбара добавлена кнопка **«⚙ НАСТРОЙКИ»** (`Ghost.TButton`),
  вызывающая `controller.open_settings()`.
- Ширина сайдбара теперь вычисляется через `ThemeManager.CONTROL["sidebar_min"/"sidebar_max"]`
  + пользовательскую настройку + `viewport_mode()`, и **пересчитывается при
  resize окна** (подписка на `ThemeManager.add_scale_listener`).
- Восстановлена опция «💻 Сист.» в переключателе темы (была удалена в
  прошлой сессии; теперь она безопасна, т.к. полный выбор живёт в Настройках).
- Сохранены все публичные методы (`get_date`, `get_curator`, `get_month_range`,
  `set_*_state`, `apply`, `set_refresh_state`, …).

### 4. `gui_master_settings.py` — mixin для GuiMaster

Добавляет 3 метода в `GuiMaster` без переписывания всего файла:
- `_init_settings(config_controller)` — загрузка prefs из `config.yaml`,
  применение к `ThemeManager`, синхронизация с сайдбаром, подписка на
  пересчёт масштаба для reflow таблицы.
- `open_settings()` — открытие `SettingsDialog`.
- `apply_ui_preferences(prefs)` — применение prefs к работающему GUI
  (вызывается диалогом на Apply/OK/Cancel).

### 5. `settings_store.py` — персистентность UI-настроек

Класс `SettingsStore` читает/пишет секцию `ui:` **в том же** `config.yaml`:

```yaml
ui:
  theme: light            # light | dark | system
  scale_mode: auto        # auto | manual
  user_scale: 1.0         # 0.80 .. 1.50
  density: normal         # compact | normal | comfortable
  sidebar_width: 0        # 0 = авто
  window_geometry: null   # "WxH+X+Y"
```

Все значения проходят валидацию и coercion — повреждённая секция `ui:`
никогда не роняет приложение (возвращаются значения по умолчанию).

---

## Шаги интеграции (3 правки в существующем коде)

### Правка 1 — `APP/core/ui/gui_master.py`

В `class GuiMaster` добавить наследование от mixin и две строки в
`__init__`:

```python
# вверху файла, рядом с другими import:
from core.ui.gui_master_settings import GuiMasterSettingsMixin
from core.ui.ui_settings import SettingsDialog  # не обязательно, mixin импортирует сам

# заголовок класса:
class GuiMaster(GuiMasterSettingsMixin):   # было: class GuiMaster:
    def __init__(self, root, config_controller, app_controller):
        ...
        ThemeManager.init_scaling(self.root)
        ThemeManager.attach_resize_listener(self.root)   # ← ДОБАВИТЬ (v5.6)
        ThemeManager.apply_styles()
        ...
        self.setup_ui()
        ...
        # в САМОМ КОНЦЕ __init__, после setup_ui:
        self._init_settings(config_controller)           # ← ДОБАВИТЬ (v5.6)
```

### Правка 2 — `APP/core/ui/ui_employee_table.py` (опционально, для reflow)

Добавить метод `reflow_columns`, пересчитывающий ширины колонок по
пропорциям (35 % / 20 % / 45 %) от текущей ширины виджета. Если метод
отсутствует, mixin просто пропустит reflow (защита `hasattr`).

### Правка 3 — скопировать 5 файлов

Скопируйте файлы из этого каталога в проект согласно таблице вверху.

---

## Проверка

```bash
python3 -m py_compile APP/core/ui/theme.py \
  APP/core/ui/ui_settings.py \
  APP/core/ui/ui_sidebar.py \
  APP/core/ui/gui_master_settings.py \
  APP/core/infra/settings_store.py
```

Затем запустите приложение как обычно. При первом запуске в `config.yaml`
появится секция `ui:`. Откройте **⚙ Настройки** в сайдбаре и убедитесь, что:
- слайдер масштаба меняет размер всего интерфейса в реальном времени;
- изменение размера окна пересчитывает ширину сайдбара и высоту строк;
- вкладка «Пути и файлы» позволяет выбрать папку сохранения отчётов;
- «Отмена» откатывает все изменения предпросмотра.

---
version: 1.0
name: Master-Report-Consolidator-design-system
description: >-
  A desktop financial-consolidation workstation ("Тихая касса" / treasury
  tool) anchored on a restrained corporate navy-blue accent (#1b4b8a
  light / #5b8def dark), warm-cool neutral surfaces, and a four-step
  Linear-style surface ladder in dark mode. Dense, precise, trustworthy —
  reads as an internal treasury instrument, not a SaaS template. Built for
  Tkinter/ttk (no radius/shadow on native widgets) with an HTML/CSS
  reference implementation for visual validation.

colors:
  primary: "#1b4b8a"
  primary-hover: "#163d70"
  primary-active: "#143560"
  primary-focus: "#5b8def"
  primary-soft: "rgba(27,75,138,0.08)"
  on-primary: "#ffffff"
  secondary: "#0e6e8c"
  on-secondary: "#ffffff"
  canvas: "#f5f6f8"
  surface-1: "#ffffff"
  surface-2: "#eceef2"
  surface-3: "#e2e5eb"
  ink: "#1a2332"
  ink-secondary: "#3d4859"
  ink-muted: "#6b7588"
  ink-subtle: "#8b94a5"
  hairline: "#e2e5eb"
  hairline-strong: "#c4cad4"
  success: "#1a8a4e"
  success-soft: "rgba(26,138,78,0.08)"
  warning: "#b45309"
  warning-soft: "rgba(180,83,9,0.08)"
  error: "#c0492f"
  error-soft: "rgba(192,73,47,0.08)"
  info: "#0e6e8c"

colors-dark:
  primary: "#5b8def"
  primary-hover: "#7aa2f7"
  primary-active: "#3b6fd0"
  primary-focus: "#5b8def"
  primary-soft: "rgba(91,141,239,0.12)"
  on-primary: "#111418"
  secondary: "#4db0c9"
  on-secondary: "#111418"
  canvas: "#111418"
  surface-1: "#171b21"
  surface-2: "#1e232b"
  surface-3: "#2a3038"
  ink: "#e7ebf3"
  ink-secondary: "#b8c0cc"
  ink-muted: "#8b94a5"
  ink-subtle: "#6b7588"
  hairline: "#232830"
  hairline-strong: "#363d48"
  success: "#5fb87a"
  success-soft: "rgba(95,184,122,0.10)"
  warning: "#e0a341"
  warning-soft: "rgba(224,163,65,0.10)"
  error: "#ec6a5f"
  error-soft: "rgba(236,106,95,0.10)"
  info: "#4db0c9"

typography:
  display:
    fontFamily: "Segoe UI Semibold, Inter, system-ui, -apple-system, sans-serif"
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.4px
  heading:
    fontFamily: "Segoe UI Semibold, Inter, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: -0.2px
  body:
    fontFamily: "Segoe UI, Inter, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-bold:
    fontFamily: "Segoe UI Semibold, Inter, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: 0
  small:
    fontFamily: "Segoe UI, Inter, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  caption:
    fontFamily: "Segoe UI, Inter, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  mono:
    fontFamily: "Cascadia Mono, JetBrains Mono, ui-monospace, Consolas, monospace"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  button:
    fontFamily: "Segoe UI Semibold, Inter, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0

rounded:
  none: 0px
  sm: 4px
  md: 6px
  lg: 8px
  xl: 12px
  pill: 9999px

spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  xxxl: 48px
  section: 64px

shadow:
  subtle: "0 1px 2px rgba(26,35,50,0.05)"
  medium: "0 4px 12px rgba(26,35,50,0.08)"
  elevated: "0 12px 32px rgba(26,35,50,0.12)"

shadow-dark:
  subtle: "0 1px 2px rgba(0,0,0,0.30)"
  medium: "0 4px 12px rgba(0,0,0,0.40)"
  elevated: "0 12px 32px rgba(0,0,0,0.50)"

---

## 1. Visual Theme & Atmosphere

**«Тихая касса» — the quiet treasury.** Master-Report Consolidator reads as an
internal instrument for a serious finance team: calm, dense, precise, and
deliberately understated. It rejects the "SaaS-startup" vocabulary (bright
gradients, playful mascots, neon accents) in favour of an institutional
navy-blue accent, warm-cool neutral surfaces, and tabular figures that align
sums to the decimal point. Trust is built through legibility and density, not
decoration. Every screen should feel like a document a treasurer would not be
ashamed to print and file.

Density is high (compact rows, multi-column dashboards, sidebar with 5 stacked
action groups) but never cramped — whitespace follows a strict 4px scale so the
eye finds structure even when the table is full. The single chromatic accent
(navy) is spent sparingly: primary CTA, active tab, focus ring, selected row.
Semantic colours (success/warning/error) are muted earth tones — a financial
alert must read serious, not panicked.

## 2. Color Palette & Roles

| Semantic name | Hex (light / dark) | Role | Where used |
|---|---|---|---|
| `primary` | `#1b4b8a` / `#5b8def` | brand accent (single) | primary CTA, active tab, focus ring, selection |
| `primary-hover` | `#163d70` / `#7aa2f7` | primary hover state | hovered primary button |
| `secondary` | `#0e6e8c` / `#4db0c9` | informational accent | info toasts, secondary actions |
| `canvas` | `#f5f6f8` / `#111418` | app background | main window background |
| `surface-1` | `#ffffff` / `#171b21` | card / panel | sidebar, tables, dialogs |
| `surface-2` | `#eceef2` / `#1e232b` | recessed zone | table headers, troughs, hover lift |
| `surface-3` | `#e2e5eb` / `#2a3038` | deepest lift | dropdowns, popovers |
| `ink` | `#1a2332` / `#e7ebf3` | primary text | body, headings, table cells |
| `ink-muted` | `#6b7588` / `#8b94a5` | secondary text | captions, placeholders, meta |
| `hairline` | `#e2e5eb` / `#232830` | 1px border | card edges, dividers |
| `hairline-strong` | `#c4cad4` / `#363d48` | input border | unfocused input border |
| `success` | `#1a8a4e` / `#5fb87a` | positive status | "готово", success toast |
| `warning` | `#b45309` / `#e0a341` | attention status | "нет данных", warning toast |
| `error` | `#c0492f` / `#ec6a5f` | negative status | "нет файла", error toast |
| `info` | `#0e6e8c` / `#4db0c9` | informational | info toast, help text |

**Accent discipline:** exactly ONE chromatic accent (`primary`). `secondary` is
reserved for informational toasts and is used <5% as often as primary.
Semantic colours never serve as brand accents — green is owned by "positive
amount" semantics in a finance tool.

**Soft variants** (`*-soft`, 8% alpha) are used for status row-washes in tables:
a ready row gets an 8% success tint, an error row an 8% error tint — scannable
without overwhelming the stripe pattern.

## 3. Typography Rules

**Font families** (system-first, cross-platform fallback):
- **UI sans:** `Segoe UI Semibold` (headings/buttons) + `Segoe UI` (body) →
  fallback `Inter, system-ui, -apple-system, sans-serif`. Semibold is named as
  a *family* (not the algorithmic `bold` flag) so Tk/Web pull the real cut.
- **Mono (sums/paths):** `Cascadia Mono` → fallback `JetBrains Mono, ui-monospace,
  Consolas, monospace`. Chosen for tabular figures — every digit has identical
  advance-width so sum columns align on the decimal point.

**Full hierarchy:**

| Level | font-size | font-weight | line-height | letter-spacing | Use |
|---|---|---|---|---|---|
| `display` | 24px | 600 | 1.25 | -0.4px | dialog titles, hero stat numbers |
| `heading` | 16px | 600 | 1.35 | -0.2px | card titles, section headers |
| `body` | 14px | 400 | 1.5 | 0 | default text, table cells |
| `body-bold` | 14px | 600 | 1.5 | 0 | status badges, emphasis |
| `small` | 13px | 400 | 1.5 | 0 | secondary body, treeview rows |
| `caption` | 12px | 400 | 1.4 | 0 | captions, helper text, meta |
| `mono` | 13px | 400 | 1.5 | 0 | sums, file paths, code |
| `button` | 14px | 600 | 1.2 | 0 | all button labels |

**Principles:** negative letter-spacing on display (tightens large text);
Semibold for emphasis (never algorithmic bold on the body family); mono ONLY
for numerics and paths — never for prose.

## 4. Component Stylings

### Buttons

| Variant | background | color | border | padding | radius |
|---|---|---|---|---|---|
| `primary` | `primary` | `on-primary` | none | `10px 16px` | `lg` (8px) |
| `secondary` | `surface-2` | `ink` | `1px hairline` | `10px 16px` | `lg` |
| `ghost` | transparent | `ink` | none | `10px 16px` | `lg` |
| `disabled` | `surface-2` | `ink-muted` | none | `10px 16px` | `lg` |

**States:**
- `:hover` — primary → `primary-hover`; secondary → `surface-3`; ghost → `surface-2`.
- `:active` — primary → `primary-active` (translateY(1px)); others darken one step.
- `:focus-visible` — `outline: 2px solid primary-focus; outline-offset: 2px`.
- `:disabled` — `opacity: 0.5; cursor: not-allowed`.

### Cards

`background: surface-1; border: 1px solid hairline; border-radius: xl (12px);
padding: lg (16px)–xl (24px); box-shadow: subtle`. Hovered/featured card lifts
to `surface-2` + `shadow: medium`.

### Inputs

| State | border | background | box-shadow |
|---|---|---|---|
| default | `1px hairline-strong` | `surface-1` | none |
| focus | `2px primary` | `surface-1` | none |
| error | `2px error` | `surface-1` | none |
| disabled | `1px hairline` | `surface-2` | none |

Input padding: `8px 12px`; radius `lg`; font `body`.

### Navigation

- **Sidebar:** fixed left, width 240–280px, `background: surface-1`, right
  `border-right: 1px hairline`. Sections separated by `padding-block: sm`.
  Active item: `background: primary-soft; color: primary; border-left: 3px solid primary`.
- **Tabs:** underline style. Active: `color: primary; border-bottom: 2px solid primary`.
  Inactive: `color: ink-muted`. Hover: `color: ink`.
- **Topbar** (if used): height 56px, `background: surface-1`, bottom hairline.

## 5. Layout Principles

**Spacing scale** (base 4px): `xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32 ·
xxxl 48 · section 64`.

**Grid:** 12-column, `max-width: 1280px` container, `gap: lg (16px)`. Sidebar
layouts use a fixed 260px rail + fluid main area.

**Whitespace philosophy:** the *canvas* is the whitespace (Linear principle).
Cards lift onto `surface-1` rather than being separated by gaps in white. Within
a card, use `lg (16px)` between blocks; between sections use `xl (24px)` or
`xxl (32px)`. Tables are dense (`row-height: 36px`) — data screens prioritise
information density over breathing room.

## 6. Depth & Elevation

Three-level shadow system (light values; dark uses stronger alphas):

| Level | box-shadow | Use |
|---|---|---|
| `subtle` | `0 1px 2px rgba(26,35,50,0.05)` | default cards, resting state |
| `medium` | `0 4px 12px rgba(26,35,50,0.08)` | hovered cards, dropdowns |
| `elevated` | `0 12px 32px rgba(26,35,50,0.12)` | dialogs, popovers, toasts |

**Primary mechanism is the surface ladder, not shadow** (Linear discipline):
canvas → surface-1 → surface-2 → surface-3 carries hierarchy through colour
contrast. Shadows are secondary, used only on transient surfaces (dialogs,
toasts) where a surface lift alone would be insufficient. On dark, shadows use
pure-black alphas (0.30/0.40/0.50).

## 7. Do's and Don'ts

### Do
- Reserve `primary` for the single most important action on each screen.
- Use `mono` font for every numeric cell and file path.
- Carry depth via the surface ladder (surface-1/2/3) before reaching for shadow.
- Apply `*-soft` (8% alpha) row-washes to communicate status at a glance.
- Set `:focus-visible` outlines on every interactive element (2px primary-focus).

### Don't
- Don't use green as a brand accent — it is semantically owned by "positive amount".
- Don't mix two bright accents in one view (e.g. primary + warning CTA side by side).
- Don't use `Cascadia Code` for sums — its ligatures break numeric alignment.
- Don't apply border-radius or box-shadow to native Tk widgets (they can't honour them).
- Don't render raw `str(exception)` to the user — route through `error_presenter`.

## 8. Responsive Behavior

| Breakpoint | Width | Key changes |
|---|---|---|
| mobile | <640px | single column, sidebar collapses to hamburger, tabs scroll |
| tablet | 640–1024px | 2-column grids, sidebar narrows to 240px |
| desktop | 1024–1440px | full sidebar + 12-col grid (default) |
| wide | >1440px | container caps at 1280px, centred with canvas margins |

**Touch targets:** minimum `44×44px` on mobile/tablet; buttons grow vertical
padding to `12px` below 1024px. Tap rows in tables expand to `48px` height on
touch viewports.

## 9. Agent Prompt Guide

**Quick reference (paste into any UI-generation prompt):**
```
Palette: primary #1b4b8a (L) / #5b8def (D), canvas #f5f6f8/#111418,
surface #ffffff/#171b21, ink #1a2332/#e7ebf3, hairline #e2e5eb/#232830.
Fonts: Segoe UI Semibold (headings/buttons), Segoe UI (body), Cascadia Mono (sums).
Spacing: 4/8/12/16/24/32/48/64. Radius: 4/6/8/12.
One accent only. Depth via surface ladder, shadow only on dialogs/toasts.
Tabular figures for all numbers. :focus-visible 2px primary-focus.
```

**Prompt 1 — Dashboard:**
> "Build a financial dashboard using DESIGN.md. Sidebar left (260px, surface-1,
> 5 action groups). Main area: KPI cards row (4 cards, mono numbers), then a
> data table (employee readiness: columns Сотрудник/Статус/Файл, status badges
> with *-soft row-washes, hover-row highlight). Light theme. Use CSS variables
> from DESIGN.md, semantic HTML, :focus-visible on all controls."

**Prompt 2 — Settings dialog:**
> "Build a modal settings dialog (elevated shadow, 8 tabs in a left rail,
> live-preview theme switch). Inputs with focus/error/disabled states. Footer
> with Cancel (ghost) + Apply (primary) buttons. ARIA: role=dialog,
> aria-labelledby. Escape to close. Use DESIGN.md tokens only."

**Prompt 3 — Consolidation results:**
> "Build a results screen: success toast (top-right, medium shadow, success-soft
> bg), a summary card (rows count, mono), and a detail table with success/error
> row tags. Empty-state placeholder when no data ('Запустите сборку отчета').
> Dark theme. Tabular figures. Hairline borders, no heavy shadows."

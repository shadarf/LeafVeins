# LeafVeins — "Overleaf" Theme Reproduction Plan

## 1. Goal

Add a first-class **Overleaf** theme to LeafVeins that visually reproduces the
VS Code extension **Overleaf Theme** by Ariq Ahmer
(`AriqAhmer.overleaf-theme`, v0.0.1), applied consistently to:

- main window chrome (menu bar, toolbars, status bar, dock widgets)
- LaTeX editor + line-number gutter + syntax highlighting
- file tree
- PDF preview pane
- compile log / console

The theme must not break the existing **Dark / Light / System** themes, must
survive an app restart, and must not regress the recently fixed compile → PDF
preview flow.

---

## 2. Source theme research (completed)

Research source: VSIX downloaded from the Marketplace URL and its
`themes/Overleaf Theme-color-theme.json` inspected directly.

- Extension type: **light** (`"uiTheme": "vs"`)
- `"semanticHighlighting": true`
- Token palette is One-Dark-like, even though the UI chrome is light.
- The VS Code repository is `https://github.com/AriqAhmer/overleaf-theme.git`.

### 2.1 UI color roles (exact values from the theme JSON)

| Role | VS Code key | Value |
|---|---|---|
| Editor background / foreground | `editor.background` / `editor.foreground` | `#ffffff` / `#000000` |
| Editor text (general) | `foreground` | `#616161` |
| Line numbers | `editorLineNumber.foreground` | `#237893` |
| Active line number | `editorLineNumber.activeForeground` | `#0b216f` |
| Current line | `editor.lineHighlightBackground` / `...Border` | `#ffffff0a` / `#eeeeee` |
| Selection | `editor.selectionBackground` | `#add6ff` |
| Inactive selection | `editor.inactiveSelectionBackground` | `#add6ff80` |
| Find match | `editor.findMatchHighlightBackground` | `#ffff00` |
| Selection highlight | `editor.selectionHighlightBackground` | `#f3f3f3` |
| Caret | `editorCursor.foreground` | `#000000` |
| Whitespace / indent guide | `editorWhitespace.foreground` / `editorIndentGuide.background1` | `#cfcfcf` / `#d3d3d3` |
| Title bar | `titleBar.activeBackground` / `.activeForeground` | `#1b222c` / `#ffffff` |
| Title bar inactive | `titleBar.inactiveBackground` / `.inactiveForeground` | `#3a3a3a` / `#ffffffcc` |
| Activity bar | `activityBar.background` / `.inactiveForeground` | `#2c2c2c` / `#ffffff` |
| Side bar | `sideBar.background` / `sideBar.foreground` | `#495365` / `#ffffff` |
| Side bar title | `sideBarTitle.foreground` | `#cccccc` |
| Tabs background | `editorGroupHeader.tabsBackground` | `#e8e8e8` |
| Active tab | `tab.activeBackground` / `.activeForeground` | `#098842` / `#ffffff` |
| Inactive tab | `tab.inactiveBackground` / `.inactiveForeground` | `#e8e8e8` / `#333333b3` |
| Tab border | `tab.border` | `#f3f3f3` |
| Status bar | `statusBar.background` / `.foreground` | `#097339` / `#ffffff` |
| Status bar hover | `statusBarItem.hoverBackground` | `#ffffff1f` |
| Buttons | `button.background` / `.foreground` / `.hoverBackground` | `#009041` / `#ffffff` / `#086231` |
| Secondary button | `button.secondaryBackground` / `.secondaryForeground` | `#5f6a79` / `#ffffff` |
| Inputs | `input.background` / `.foreground` / `.border` / `.placeholderForeground` | `#ffffff` / `#616161` / `#5d6166` / `#61616180` |
| List hover / active selection | `list.hoverBackground` / `list.activeSelectionBackground` | `#ffffff1a` / `#5a6a7a` |
| List inactive selection | `list.inactiveSelectionBackground` | `#5a6a7a80` |
| List highlight | `list.highlightForeground` | `#098842` |
| Dropdown list | `list.focusBackground` / `list.focusForeground` | `#04395e` / `#ffffff` |
| Combo/item selection | `list.selectionBackground` / `.selectionForeground` | `#094771` / `#ffffff` |
| Widgets | `editorWidget.background` / `.foreground` / `.border` | `#f3f3f3` / `#616161` / `#c7c7c7` |
| Widget shadow | `widget.shadow` | `#00000029` |
| Picker group | `pickerGroup.border` / `.foreground` | `#cccedb` / `#0a6f37` |
| Debug toolbar | `debugToolBar.background` / `.border` | `#f3f3f3` / `#cccedb` |
| Breadcrumb | `breadcrumb.background` / `.foreground` / `.focusForeground` | `#ffffff` / `#616161cc` / `#4e4e4e` |
| Scrollbar thumb | `scrollbarSlider.background` | `#64646466` |
| Scrollbar hover / active | `scrollbarSlider.hoverBackground` / `.activeBackground` | `#646464b3` / `#00000099` |
| Scrollbar shadow / separator | `scrollbar.shadow` / `editorGutter.background` | `#dddddd` / `#ffffff` |
| Progress bar | `progressBar.background` | `#098842` |

Semantic token colors from the theme JSON:

| Semantic token | Color |
|---|---|
| `enumMember` | `#56b6c2` |
| `variable.constant` | `#d19a66` |
| `variable.defaultLibrary` | `#e5c07b` |

### 2.2 Token colors relevant to LaTeX

Selected directly from the theme's `tokenColors` (One Dark palette):

| Token role | VS Code scope | Color |
|---|---|---|
| Heading / sectioning | `markup.heading` | `#e06c75` |
| Emphasis / italic | `markup.italic` | `#c678dd` |
| Bold | `markup.bold` | `#e5c07b` |
| Keywords | `keyword` | `#c678dd` |
| Functions / commands | `entity.name.function` | `#61afef` |
| Strings | `string` | `#98c379` |
| Numbers | `constant.numeric` | `#d19a66` |
| Constants | `constant` | `#e5c07b` |
| Types / support | `support.type` | `#e5c07b` |
| Variables | `variable` | `#e06c75` |
| Comments | `comment` | `#7f848e` (italic) |
| Punctuation / plain text | `punctuation`, default | `#000000` |
| Invalid / brackets | `invalid`, `punctuation.definition.bracket` | `#f44747` |
| Link / URL | `markup.underline.link` | `#61afef` |
| Reference-like data | `enumMember` / constant | `#56b6c2` |

---

## 3. Current LeafVeins theming architecture

- Theme identity is a single string in config: `ui.theme` (`dark` / `light` / `system`).
- `app/core/app.py`
  - `_setup_menu()` creates checkable **Dark / Light / System** actions (lines ~204–213).
  - `set_theme()` (lines ~397–521) sets menu checks, forwards the theme to
    editor, file tree, PDF viewer and log widget, then applies a large
    `if theme == "dark": ... else: ...` stylesheet to `QMainWindow`.
  - `_setup_toolbar()` (lines ~265–307) creates actions with no `objectName`,
    so a single Compile button cannot be styled independently yet.
  - `_setup_statusbar()` uses plain `QLabel`s that inherit the main stylesheet.
- `app/ui/editor/highlighter.py`
  - `LatexHighlighter._setup_formats()` hardcodes two format dictionaries.
  - `_setup_rules()` holds the LaTeX regex rules; `set_theme()` swaps the dict
    but currently **skips `rehighlight()`** (comment says to avoid a crash), so
    an already-open document does not recolor when the theme changes.
- `app/ui/editor/editor_widget.py`
  - `LatexEditor.set_theme()` hardcodes editor colors.
  - `LineNumberArea` / `line_number_area_paint_event()` hardcode `#282c34`,
    `#5c6370`; `_highlight_current_line()` hardcodes `#3b4048`.
- `app/ui/file_tree/file_tree_widget.py` — `set_theme()` hardcodes tree colors.
- `app/ui/preview/pdf_viewer.py` — `set_theme()` hardcodes viewer colors.
- `app/ui/console/log_widget.py` — `set_theme()` hardcodes log colors.
- Build is `python build.py` (PyInstaller one-file). Theme work is pure
  Python/QSS; no new binary dependency is required.

---

## 4. Implementation plan

### Phase A — Central theme registry (single source of truth)

**New file:** `app/core/themes.py`

1. Define a `ThemePalette` dataclass (or plain dict) with named roles matching
   Section 2.1: `editor_bg`, `editor_fg`, `foreground`, `line_number`,
   `line_number_active`, `current_line_bg`, `current_line_border`, `selection`,
   `selection_inactive`, `caret`, `gutter`, `title_bg`, `title_fg`,
   `activity_bg`, `side_bg`, `side_fg`, `tab_bg`, `tab_active_bg`,
   `tab_active_fg`, `tab_inactive_fg`, `status_bg`, `status_fg`,
   `button_bg`, `button_fg`, `button_hover`, `button_secondary`, `input_bg`,
   `input_fg`, `input_border`, `list_hover`, `list_selection`, `widget_bg`,
   `widget_fg`, `widget_border`, `scroll_thumb`, `progress`, `error`,
   `warning`, `info`, `success`, plus syntax roles from Section 2.2.
2. Add `THEMES = {"dark": ..., "light": ..., "overleaf": ...}`.
   - Migrate the **existing** dark/light hex values verbatim so those themes do
     not visually change.
   - Populate `overleaf` from the exact values in Section 2.
3. Provide `get_palette(theme: str) -> ThemePalette`. Resolve `"system"` by
   checking the OS setting (dark/light) and returning the matching palette;
   `"overleaf"` is always itself.
4. Provide a small QSS helper, e.g. `qss(template: str, p: ThemePalette) -> str`,
   or use `str.format(**p.as_dict())`, so stylesheets are generated from the
   palette rather than literal hex strings.

### Phase B — Theme selection wiring

**Files:** `app/core/config.py`, `app/core/app.py`

1. `ui.theme` already exists; document that it now also accepts `"overleaf"`.
   Keep the default unchanged (`dark`).
2. In `_setup_menu()` add:
   - `self.theme_overleaf_action = theme_menu.addAction("Overleaf")`
   - `setCheckable(True)`
   - `triggered.connect(lambda: self.set_theme("overleaf"))`
3. In `set_theme()` extend the checked-state updates:
   - `self.theme_overleaf_action.setChecked(theme == "overleaf")`
4. Replace the big `if/else` stylesheet with `get_palette(theme)` + generated
   QSS from Phase A, using the Overleaf mappings in Phase F.

### Phase C — Syntax highlighting

**File:** `app/ui/editor/highlighter.py`

1. Refactor `_setup_formats()` to read colors from `get_palette(self.theme)`
   for **all three** themes.
2. Keep existing rule regexes; add/verify categories so the Overleaf mapping
   can be expressed:

   | Category | Rule to add/refine | Overleaf color |
   |---|---|---|
   | `heading` | `\section`, `\chapter`, `\subsection`, etc. | `#e06c75`, bold |
   | `command` | generic `\command` | `#61afef` |
   | `environment` | `\begin{...}` / `\end{...}` names | `#e5c07b` |
   | `keyword` | structural keywords | `#c678dd` |
   | `comment` | `% ...` | `#7f848e`, italic |
   | `math` | `$...$`, `\(...\)`, `\[...\]` | `#e5c07b` |
   | `number` | digits in math/text | `#d19a66` |
   | `string` | quoted text / URLs | `#98c379` |
   | `reference` | `\ref`, `\cite`, `\label` arguments | `#56b6c2` |
   | `brace` | `{ } [ ]` | `#000000` |
   | `invalid` | unmatched brackets | `#f44747` |

   Rationale: map LaTeX constructs onto the VS Code scopes the theme actually
   styles, not onto the Overleaf web editor's own palette.
3. Fix theme switching so open documents recolor:
   - In `set_theme()`, after rebuilding formats, schedule
     `QTimer.singleShot(0, self.rehighlight)` instead of calling it inline
     (avoids the reentrancy issue that led to the old "skip rehighlight"
     workaround). Verify no crash; if it still crashes, recreate the highlighter
     after the stylesheet update.
4. Acceptance: switching Dark → Overleaf → Light while a `.tex` file is open
   recolors every token immediately and does not crash.

### Phase D — Editor and gutter

**File:** `app/ui/editor/editor_widget.py`

1. `LatexEditor.set_theme()` use palette values:
   - background `#ffffff`, foreground `#000000`
   - selection `#add6ff`, border `#eeeeee` (or `#d3d3d3`)
   - line-number area background `#ffffff`
2. Replace hardcoded colors in:
   - `line_number_area_paint_event()` → gutter `#ffffff`, normal numbers
     `#237893`, current number `#0b216f`
   - `_highlight_current_line()` → `#ffffff0a` (alpha!) and border `#eeeeee`
3. Alpha colors: use a helper that builds `QColor` with explicit alpha (e.g.
   `QColor(255, 255, 255, 10)`) for painter code; QSS can use `#ffffff0a` /
   `rgba(255,255,255,10)` directly.
4. `EditorWidget`'s own toolbar should inherit palette toolbar colors.

### Phase E — File tree, PDF preview, log console

**Files:** `app/ui/file_tree/file_tree_widget.py`,
`app/ui/preview/pdf_viewer.py`, `app/ui/console/log_widget.py`

Overleaf palette application:

| Widget | Overleaf colors |
|---|---|
| File tree | tree bg `#495365`, fg `#ffffff`; selected `#098842`; hover `#ffffff1a`; toolbar `#2c2c2c`; filter input `#ffffff` / `#616161`, border `#5d6166`; scrollbars from palette |
| PDF viewer | background `#ffffff`; toolbar `#f3f3f3`; page area `#ffffff`; page border/shadow `#d3d3d3` / `#00000029`; controls `#616161`; selection `#add6ff` |
| Log console | background `#ffffff`; text `#616161`; toolbar `#f3f3f3`; error `#e51400`, warning `#e9a700`, info `#75beff`, success `#98c379` |

Notes:
- Do **not** touch the PDF pixel-copy rendering fix from the previous task;
  only change stylesheets.
- Check `log_widget.append()` message-level → color mapping and add a palette
  lookup so log levels use the theme's semantic colors.

### Phase F — Main window chrome

**Files:** `app/core/app.py` (and `editor_widget.py` for toolbar button object name)

1. In `_setup_toolbar()`, set `self.compile_btn.setObjectName("CompileButton")`
   and optionally `self.stop_btn.setObjectName("StopButton")` so the compile
   action can get the theme's green button treatment:
   - `QToolButton#CompileButton { background:#009041; color:#ffffff; }`
   - hover `#086231`, disabled `#5f6a79`, pressed `#086231`
   - Stop button uses the secondary button palette.
2. Generate the full `QMainWindow` QSS from the palette. Overleaf mapping:

   | Qt selector | Overleaf style |
   |---|---|
   | `QMainWindow`, `QWidget` | bg `#ffffff`, fg `#000000` |
   | `QMenuBar` | bg `#1b222c`, fg `#ffffff`; item selected `#098842` |
   | `QMenu` | bg `#ffffff`, fg `#616161`, border `#d5d5d5`; item selected `#094771` / `#ffffff` |
   | `QToolBar` | bg `#f3f3f3`, border `#d5d5d5`; button hover `#ffffff1a` |
   | `QStatusBar` | bg `#097339`, fg `#ffffff`; item hover `#ffffff1f` |
   | `QSplitter::handle` | `#dddddd` (or `#495365` for the tree split) |
   | `QDockWidget::title` | bg `#f3f3f3`, fg `#616161`, border `#d5d5d5` |
   | `QComboBox`, `QSpinBox`, `QLineEdit` | bg `#ffffff`, fg `#616161`, border `#5d6166`; focus border `#04395e` |
   | `QScrollBar` | thumb `#64646466`, hover `#646464b3`, active `#00000099`, shadow `#dddddd` |
   | `QProgressBar` | chunk `#098842` |
   | `QTabWidget` / tab bar | bar `#e8e8e8`, active tab `#098842` / `#ffffff`, inactive `#333333b3` |

3. Ensure `set_theme()` calls each child `set_theme()` **before** applying the
   main stylesheet, so child QSS wins where needed.

### Phase G — Build and verification

1. No new build dependencies; run `python build.py` after implementation to
   refresh `dist\LeafVeins.exe`.
2. Verification checklist:
   - [ ] App launches from source and from `dist\LeafVeins.exe`.
   - [ ] View → Theme shows four checkable items; only the active one is checked.
   - [ ] Selecting **Overleaf** immediately recolors open `.tex` files.
   - [ ] Theme choice persists after restart (`ui.theme` in config).
   - [ ] Open `TEST_projects\01_Test1\main.tex`; colors match Section 2.2;
         line numbers are teal and the current line has the subtle highlight.
   - [ ] File tree still shows `.tex` and hides `.aux`/`.pdf` (regression check
         for the earlier filter fix).
   - [ ] Press **F5**: Compile button is green during compilation; green status
         bar progress appears; PDF shows in the white preview pane; **app stays
         open** (regression check for the earlier `ImageQt` crash).
   - [ ] Switch Dark → Overleaf → Light several times with no crash or stale
         colors.
   - [ ] Compare a screenshot side-by-side with the VS Code theme preview
         (`https://vscodethemes.com/e/AriqAhmer.overleaf-theme/overleaf-theme`).
   - [ ] Rebuild exe and repeat the smoke test.

---

## 5. Risks and decisions

1. **8-digit hex colors** (`#ffffff0a`): Qt stylesheets accept `#AARRGGBB`, but
   `QPainter` code should pass explicit alpha to `QColor`. Centralize conversion
   in the palette helper.
2. **Rehighlight crash**: previously disabled. Defer with
   `QTimer.singleShot(0, ...)` and test explicitly; do not leave theme switches
   half-applied.
3. **`system` theme**: currently behaves as Light. Preserve that behavior;
   `"overleaf"` is a distinct explicit choice.
4. **Provenance**: the reference theme JSON is from
   `AriqAhmer.overleaf-theme@0.0.1`. Optionally commit a copy under
   `theme/reference/` during implementation so the palette can be re-checked.
5. **Scope boundary**: this plan changes presentation only; compiler, file-tree
   filtering and PDF rendering logic stay untouched.

---

## 6. Suggested file-change summary (for implementation)

| File | Change |
|---|---|
| `app/core/themes.py` | **new** — palette registry + QSS helper |
| `app/core/app.py` | Overleaf menu action; palette-driven main QSS; compile button object name |
| `app/ui/editor/highlighter.py` | palette-driven formats; new token categories; safe rehighlight |
| `app/ui/editor/editor_widget.py` | palette-driven editor/gutter/current-line colors |
| `app/ui/file_tree/file_tree_widget.py` | palette-driven tree styling |
| `app/ui/preview/pdf_viewer.py` | palette-driven viewer styling only |
| `app/ui/console/log_widget.py` | palette-driven log styling and level colors |
| `build.py` | unchanged (rebuild only) |

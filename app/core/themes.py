"""Central theme palettes for LeafVeins.

Every colour used by the UI and the LaTeX highlighter lives here so themes can
be switched consistently from a single source of truth.

The ``overleaf`` palette reproduces the VS Code extension
``AriqAhmer.overleaf-theme`` (v0.0.1).  The ``dark`` and ``light`` palettes keep
the colours LeafVeins already shipped with.
"""

import re
from dataclasses import asdict, dataclass
from string import Template


@dataclass(frozen=True)
class ThemePalette:
    """All colour roles consumed by the application stylesheets."""

    name: str

    # Global window chrome
    window_bg: str
    window_fg: str
    foreground: str
    menubar_bg: str
    menubar_fg: str
    menubar_selected_bg: str
    menu_bg: str
    menu_fg: str
    menu_border: str
    menu_selected_bg: str
    menu_selected_fg: str
    toolbar_bg: str
    toolbar_border: str
    toolbar_button_hover: str
    toolbar_button_pressed: str
    status_bg: str
    status_fg: str
    status_border: str
    dock_bg: str
    dock_title_bg: str
    dock_title_fg: str
    dock_border: str
    splitter_bg: str

    # Buttons and form widgets
    button_bg: str
    button_fg: str
    button_hover: str
    button_pressed: str
    button_secondary_bg: str
    button_secondary_fg: str
    button_disabled_bg: str
    button_disabled_fg: str
    input_bg: str
    input_fg: str
    input_border: str
    input_focus_border: str
    combo_bg: str
    combo_fg: str
    combo_border: str
    combo_item_selected_bg: str
    combo_item_selected_fg: str
    scroll_thumb: str
    scroll_thumb_hover: str
    scroll_thumb_active: str
    scroll_shadow: str
    progress_bg: str

    # Editor
    editor_bg: str
    editor_fg: str
    editor_selection: str
    editor_selection_inactive: str
    editor_border: str
    line_number_bg: str
    line_number_fg: str
    line_number_active_fg: str
    current_line_bg: str
    current_line_border: str
    caret: str
    gutter_bg: str
    indent_guide: str

    # File tree
    tree_bg: str
    tree_fg: str
    tree_selected_bg: str
    tree_hover_bg: str
    tree_toolbar_bg: str
    tree_filter_bg: str
    tree_filter_fg: str
    tree_filter_border: str

    # PDF preview
    pdf_bg: str
    pdf_toolbar_bg: str
    pdf_scroll_bg: str
    pdf_page_bg: str
    pdf_page_border: str
    pdf_widget_bg: str
    pdf_widget_fg: str
    pdf_widget_border: str
    pdf_shadow: str

    # Compile log
    log_bg: str
    log_fg: str
    log_toolbar_bg: str
    log_checkbox_fg: str
    log_combo_bg: str
    log_combo_fg: str
    log_combo_border: str
    log_error: str
    log_warning: str
    log_info: str
    log_success: str
    log_file: str

    # LaTeX syntax highlighting
    syn_command: str
    syn_command_bold: bool
    syn_environment: str
    syn_environment_bold: bool
    syn_math: str
    syn_comment: str
    syn_comment_italic: bool
    syn_heading: str
    syn_heading_bold: bool
    syn_keyword: str
    syn_keyword_bold: bool
    syn_brace: str
    syn_bracket: str
    syn_text: str
    syn_number: str
    syn_string: str
    syn_reference: str
    syn_reference_bold: bool
    syn_citation: str
    syn_citation_bold: bool
    syn_file: str
    syn_file_italic: bool
    syn_url: str
    syn_url_underline: bool
    syn_invalid: str

    def as_dict(self) -> dict:
        """Return a flat mapping for stylesheet substitution."""
        return asdict(self)


DARK = ThemePalette(
    name="dark",
    window_bg="#282c34", window_fg="#abb2bf", foreground="#abb2bf",
    menubar_bg="#21252b", menubar_fg="#abb2bf", menubar_selected_bg="#3e4451",
    menu_bg="#282c34", menu_fg="#abb2bf", menu_border="#3e4451",
    menu_selected_bg="#3e4451", menu_selected_fg="#ffffff",
    toolbar_bg="#21252b", toolbar_border="none",
    toolbar_button_hover="#3e4451", toolbar_button_pressed="#4b5263",
    status_bg="#21252b", status_fg="#abb2bf", status_border="#3e4451",
    dock_bg="#282c34", dock_title_bg="#21252b", dock_title_fg="#abb2bf",
    dock_border="#3e4451", splitter_bg="#3e4451",
    button_bg="#3e4451", button_fg="#abb2bf", button_hover="#4b5263",
    button_pressed="#5c6370", button_secondary_bg="#3e4451",
    button_secondary_fg="#abb2bf", button_disabled_bg="#3b4048",
    button_disabled_fg="#7f848e",
    input_bg="#282c34", input_fg="#abb2bf", input_border="#3e4451",
    input_focus_border="#61afef", combo_bg="#282c34", combo_fg="#abb2bf",
    combo_border="#3e4451", combo_item_selected_bg="#3e4451",
    combo_item_selected_fg="#ffffff",
    scroll_thumb="#3e4451", scroll_thumb_hover="#4b5263",
    scroll_thumb_active="#5c6370", scroll_shadow="#21252b",
    progress_bg="#61afef",
    editor_bg="#282c34", editor_fg="#abb2bf", editor_selection="#3e4451",
    editor_selection_inactive="#3b4048", editor_border="#3e4451",
    line_number_bg="#282c34", line_number_fg="#5c6370",
    line_number_active_fg="#abb2bf", current_line_bg="#3b4048",
    current_line_border="#3b4048", caret="#abb2bf", gutter_bg="#282c34",
    indent_guide="#3e4451",
    tree_bg="#282c34", tree_fg="#abb2bf", tree_selected_bg="#3e4451",
    tree_hover_bg="#3b4048", tree_toolbar_bg="#21252b",
    tree_filter_bg="#282c34", tree_filter_fg="#abb2bf",
    tree_filter_border="#3e4451",
    pdf_bg="#282c34", pdf_toolbar_bg="#21252b", pdf_scroll_bg="#282c34",
    pdf_page_bg="#1e2127", pdf_page_border="#3e4451", pdf_widget_bg="#282c34",
    pdf_widget_fg="#abb2bf", pdf_widget_border="#3e4451", pdf_shadow="#21252b",
    log_bg="#1e1e1e", log_fg="#abb2bf", log_toolbar_bg="#21252b",
    log_checkbox_fg="#abb2bf", log_combo_bg="#282c34", log_combo_fg="#abb2bf",
    log_combo_border="#3e4451", log_error="#e06c75", log_warning="#e5c07b",
    log_info="#56b6c2", log_success="#98c379", log_file="#c678dd",
    syn_command="#c678dd", syn_command_bold=True,
    syn_environment="#61afef", syn_environment_bold=True,
    syn_math="#e5c07b", syn_comment="#5c6370", syn_comment_italic=True,
    syn_heading="#e06c75", syn_heading_bold=True,
    syn_keyword="#e06c75", syn_keyword_bold=True,
    syn_brace="#abb2bf", syn_bracket="#abb2bf", syn_text="#abb2bf",
    syn_number="#d19a66", syn_string="#98c379",
    syn_reference="#56b6c2", syn_reference_bold=True,
    syn_citation="#c678dd", syn_citation_bold=True,
    syn_file="#e5c07b", syn_file_italic=True,
    syn_url="#56b6c2", syn_url_underline=True, syn_invalid="#f44747",
)

LIGHT = ThemePalette(
    name="light",
    window_bg="#ffffff", window_fg="#000000", foreground="#000000",
    menubar_bg="#f0f0f0", menubar_fg="#000000", menubar_selected_bg="#add6ff",
    menu_bg="#ffffff", menu_fg="#000000", menu_border="#cccccc",
    menu_selected_bg="#add6ff", menu_selected_fg="#000000",
    toolbar_bg="#f0f0f0", toolbar_border="none",
    toolbar_button_hover="#e5e5e5", toolbar_button_pressed="#d5d5d5",
    status_bg="#f0f0f0", status_fg="#000000", status_border="#cccccc",
    dock_bg="#ffffff", dock_title_bg="#f0f0f0", dock_title_fg="#000000",
    dock_border="#cccccc", splitter_bg="#cccccc",
    button_bg="#f0f0f0", button_fg="#000000", button_hover="#e5e5e5",
    button_pressed="#d5d5d5", button_secondary_bg="#f0f0f0",
    button_secondary_fg="#000000", button_disabled_bg="#f5f5f5",
    button_disabled_fg="#999999",
    input_bg="#ffffff", input_fg="#000000", input_border="#cccccc",
    input_focus_border="#0078d4", combo_bg="#ffffff", combo_fg="#000000",
    combo_border="#cccccc", combo_item_selected_bg="#add6ff",
    combo_item_selected_fg="#000000",
    scroll_thumb="#c1c1c1", scroll_thumb_hover="#a0a0a0",
    scroll_thumb_active="#808080", scroll_shadow="#f0f0f0",
    progress_bg="#0078d4",
    editor_bg="#ffffff", editor_fg="#000000", editor_selection="#add6ff",
    editor_selection_inactive="#e5e5e5", editor_border="#cccccc",
    line_number_bg="#f0f0f0", line_number_fg="#808080",
    line_number_active_fg="#000000", current_line_bg="#f0f0f0",
    current_line_border="#e5e5e5", caret="#000000", gutter_bg="#f0f0f0",
    indent_guide="#d3d3d3",
    tree_bg="#ffffff", tree_fg="#000000", tree_selected_bg="#add6ff",
    tree_hover_bg="#e5e5e5", tree_toolbar_bg="#f0f0f0",
    tree_filter_bg="#ffffff", tree_filter_fg="#000000",
    tree_filter_border="#cccccc",
    pdf_bg="#ffffff", pdf_toolbar_bg="#f0f0f0", pdf_scroll_bg="#f5f5f5",
    pdf_page_bg="#ffffff", pdf_page_border="#cccccc", pdf_widget_bg="#ffffff",
    pdf_widget_fg="#000000", pdf_widget_border="#cccccc", pdf_shadow="#ffffff",
    log_bg="#ffffff", log_fg="#000000", log_toolbar_bg="#f0f0f0",
    log_checkbox_fg="#000000", log_combo_bg="#ffffff", log_combo_fg="#000000",
    log_combo_border="#cccccc", log_error="#e06c75", log_warning="#b8860b",
    log_info="#008b8b", log_success="#008000", log_file="#800080",
    syn_command="#800080", syn_command_bold=True,
    syn_environment="#0000ff", syn_environment_bold=True,
    syn_math="#b8860b", syn_comment="#808080", syn_comment_italic=True,
    syn_heading="#ff0000", syn_heading_bold=True,
    syn_keyword="#ff0000", syn_keyword_bold=True,
    syn_brace="#000000", syn_bracket="#000000", syn_text="#000000",
    syn_number="#ff8c00", syn_string="#008000",
    syn_reference="#008b8b", syn_reference_bold=True,
    syn_citation="#800080", syn_citation_bold=True,
    syn_file="#b8860b", syn_file_italic=True,
    syn_url="#0000ff", syn_url_underline=True, syn_invalid="#ff0000",
)

OVERLEAF = ThemePalette(
    name="overleaf",
    # Matches the light Overleaf web editor reference (theme/overleaf_web_latex_editor.html).
    window_bg="#f4f6f9", window_fg="#334155", foreground="#334155",
    menubar_bg="#2c3645", menubar_fg="#ffffff", menubar_selected_bg="#384457",
    menu_bg="#ffffff", menu_fg="#334155", menu_border="#d7dce4",
    menu_selected_bg="#e2e8f0", menu_selected_fg="#0f172a",
    toolbar_bg="#f8fafc", toolbar_border="1px solid #d7dce4",
    toolbar_button_hover="#e2e8f0", toolbar_button_pressed="#cbd5e1",
    status_bg="#f8fafc", status_fg="#64748b", status_border="#d7dce4",
    dock_bg="#ffffff", dock_title_bg="#f8fafc", dock_title_fg="#334155",
    dock_border="#d7dce4", splitter_bg="#d7dce4",
    button_bg="#2fbcbc", button_fg="#ffffff", button_hover="#2fbcbc",
    button_pressed="#2fbcbc", button_secondary_bg="#ffffff",
    button_secondary_fg="#334155", button_disabled_bg="#e2e8f0",
    button_disabled_fg="#94a3b8",
    input_bg="#ffffff", input_fg="#0f172a", input_border="#cbd5e1",
    input_focus_border="#2fbcbc", combo_bg="#ffffff", combo_fg="#0f172a",
    combo_border="#cbd5e1", combo_item_selected_bg="#2fbcbc",
    combo_item_selected_fg="#ffffff",
    scroll_thumb="#cbd5e1", scroll_thumb_hover="#aab4c4",
    scroll_thumb_active="#94a3b8", scroll_shadow="#f4f6f9",
    progress_bg="#2fbcbc",
    editor_bg="#ffffff", editor_fg="#24292f", editor_selection="#2fbcbc38",
    editor_selection_inactive="#2fbcbc20", editor_border="#e2e8f0",
    line_number_bg="#f8fafc", line_number_fg="#94a3b8",
    line_number_active_fg="#475569", current_line_bg="#388bfd14",
    current_line_border="#388bfd24", caret="#1e2530", gutter_bg="#f8fafc",
    indent_guide="#e2e8f0",
    tree_bg="#f4f6f9", tree_fg="#334155", tree_selected_bg="#2fbcbc",
    tree_hover_bg="#e8edf3", tree_toolbar_bg="#ebeff5",
    tree_filter_bg="#ffffff", tree_filter_fg="#334155",
    tree_filter_border="#cbd5e1",
    pdf_bg="#e4e8ee", pdf_toolbar_bg="#f8fafc", pdf_scroll_bg="#e4e8ee",
    pdf_page_bg="#ffffff", pdf_page_border="#d7dce4", pdf_widget_bg="#ffffff",
    pdf_widget_fg="#334155", pdf_widget_border="#cbd5e1", pdf_shadow="#00000029",
    log_bg="#ffffff", log_fg="#334155", log_toolbar_bg="#f8fafc",
    log_checkbox_fg="#334155", log_combo_bg="#ffffff", log_combo_fg="#334155",
    log_combo_border="#cbd5e1", log_error="#dc2626", log_warning="#d97706",
    log_info="#0284c7", log_success="#2fbcbc", log_file="#7c3aed",
    syn_command="#0550ae", syn_command_bold=False,
    syn_environment="#8250df", syn_environment_bold=True,
    syn_math="#116329", syn_comment="#6e7781", syn_comment_italic=True,
    syn_heading="#8250df", syn_heading_bold=True,
    syn_keyword="#0550ae", syn_keyword_bold=False,
    syn_brace="#cf222e", syn_bracket="#953800", syn_text="#24292f",
    syn_number="#0550ae", syn_string="#0a3069",
    syn_reference="#0550ae", syn_reference_bold=False,
    syn_citation="#0a3069", syn_citation_bold=False,
    syn_file="#953800", syn_file_italic=True,
    syn_url="#0550ae", syn_url_underline=True, syn_invalid="#cf222e",
)


THEMES = {
    "dark": DARK,
    "light": LIGHT,
    "overleaf": OVERLEAF,
}


def resolve_theme(theme: str) -> str:
    """Resolve a configured theme name to a concrete palette name.

    ``system`` historically rendered as the light theme in LeafVeins, so that
    behaviour is preserved rather than guessing the OS preference.
    """
    if theme in THEMES:
        return theme
    return "light"


def get_palette(theme: str) -> ThemePalette:
    """Return the palette for ``theme``, falling back to Light."""
    return THEMES[resolve_theme(theme)]


_ALPHA_COLOUR = re.compile(r"^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})$")


def _rgba(value: str) -> tuple:
    """Convert a CSS-style ``#RRGGBBAA`` value into RGBA components."""
    match = _ALPHA_COLOUR.match(value)
    if not match:
        return None
    rgb = match.group(1)
    return (
        int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16),
        int(match.group(2), 16),
    )


def css_color(value: str) -> str:
    """Return a Qt-safe CSS colour string.

    Qt expects ``#AARRGGBB`` for eight-digit colours, while the source theme
    uses CSS's ``#RRGGBBAA``.  Convert the latter to ``rgba()`` unambiguously.
    """
    components = _rgba(value)
    if components is None:
        return value
    r, g, b, a = components
    return f"rgba({r}, {g}, {b}, {a})"


def qcolor(value: str):
    """Return a ``QColor`` for any palette colour string."""
    from PyQt6.QtGui import QColor

    components = _rgba(value)
    if components is None:
        return QColor(value)
    return QColor(*components)


def qss(template: str, palette: ThemePalette) -> str:
    """Substitute ``$role`` placeholders in a stylesheet with palette values.

    ``string.Template`` is used instead of ``str.format`` because QSS is full
    of literal braces that would otherwise need escaping.
    """
    values = {
        key: css_color(value) if isinstance(value, str) else value
        for key, value in palette.as_dict().items()
    }
    return Template(template).substitute(values)


# Design tokens from the Overleaf web reference that are not palette roles.
# Keeping them separate avoids forcing every theme to carry browser-only roles.
OVERLEAF_WEB_TOKENS = {
    "ol_header_bg": "#2c3645",
    "ol_header_hover": "#384457",
    "ol_header_fg": "#ffffff",
    "ol_header_muted": "#cbd5e1",
    "ol_header_border": "#1e2530",
    "ol_green": "#2fbcbc",
    "ol_green_hover": "#2fbcbc",
    "ol_green_light": "#2fbcbc",
    "ol_sidebar_bg": "#f4f6f9",
    "ol_sidebar_toolbar_bg": "#ebeff5",
    "ol_border": "#d7dce4",
    "ol_toolbar_bg": "#f8fafc",
    "ol_footer_bg": "#f8fafc",
    "ol_text": "#334155",
    "ol_muted": "#64748b",
    "ol_pdf_bg": "#e4e8ee",
    "ol_white": "#ffffff",
    "ol_shadow": "#00000029",
    "ol_amber": "#d97706",
}


def web_qss(template: str) -> str:
    """Substitute ``$ol_*`` tokens from the Overleaf web reference."""
    return Template(template).substitute(OVERLEAF_WEB_TOKENS)

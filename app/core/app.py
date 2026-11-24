"""Main application class for LeafVeins."""

import sys
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QMenuBar, QStatusBar, QToolBar, QMessageBox,
    QFileDialog, QInputDialog, QDockWidget, QLabel, QProgressBar, QComboBox,
    QToolButton, QFrame, QMenu
)
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont, QShortcut, QPixmap
from PyQt6.QtCore import Qt, QTimer, QSettings, pyqtSignal, QSize, QPoint, QRect

from core.config import get_config, Config
from core.themes import get_palette, qss, web_qss
from core.database import get_database, Database
from project.project_manager import get_project_manager, ProjectManager, ProjectInfo
from ui.editor.editor_widget import EditorWidget
from ui.file_tree.file_tree_widget import FileTreeWidget
from ui.preview.pdf_viewer import PDFViewer
from ui.console.log_widget import LogWidget
from compiler.compiler_manager import CompilerManager, CompilationResult, CompilationStatus


def resource_path(*parts: str) -> Path:
    """Resolve bundled resources in both source and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "resources"
    else:
        base = Path(__file__).resolve().parents[1] / "resources"
    return base.joinpath(*parts)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.config = get_config()
        self.db = get_database()
        self.project_manager = get_project_manager()
        self.compiler_manager = CompilerManager(self.config)
        
        self.current_file_path = None
        self.is_compiling = False
        
        self._setup_ui()
        self._setup_toolbar()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._connect_signals()
        self._apply_theme()
        self._restore_settings()
        
        # Auto-detect compilers
        self.config.auto_configure_compilers()
        
        # Show welcome screen or last project
        self._show_welcome()
    
    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        self.setWindowTitle("LeafVeins - LaTeX Editor")
        self.setMinimumSize(1200, 800)
        icon_path = resource_path("icons", "app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Central widget with an optional Overleaf-style header and splitters.
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.overleaf_header = self._create_overleaf_header()
        self.overleaf_header.setVisible(False)
        central_layout.addWidget(self.overleaf_header)

        # Main horizontal splitter (file tree | editor + preview)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        central_layout.addWidget(self.main_splitter, 1)
        
        # Left: File tree
        self.file_tree = FileTreeWidget()
        self.file_tree.setMinimumWidth(200)
        self.file_tree.setMaximumWidth(400)
        self.main_splitter.addWidget(self.file_tree)
        
        # Center: Editor + Preview (vertical splitter)
        self.center_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.center_splitter)
        
        # Editor
        self.editor = EditorWidget()
        self.center_splitter.addWidget(self.editor)
        
        # Right: PDF Preview
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.setMinimumWidth(300)
        self.center_splitter.addWidget(self.pdf_viewer)
        
        # Set splitter sizes
        self.main_splitter.setSizes([250, 950])
        self.center_splitter.setSizes([600, 400])
        
        # Bottom: Console (dock widget)
        self.console_dock = QDockWidget("Console", self)
        self.console_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.log_widget = LogWidget()
        self.console_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)
        self.console_dock.hide()  # Hidden by default

        # Lightweight Overleaf-style toast notification.
        self.toast_label = QLabel(central)
        self.toast_label.setObjectName("OverleafToast")
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_label.setVisible(False)

    def _create_overleaf_header(self) -> QWidget:
        """Build the 48px Overleaf web-style top navigation bar."""
        header = QFrame()
        header.setObjectName("OverleafHeader")
        header.setFixedHeight(48)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        menu_button = QToolButton()
        menu_button.setText("☰  Menu")
        menu_button.setObjectName("HeaderMenuButton")
        menu_button.clicked.connect(self._show_header_menu)
        layout.addWidget(menu_button)

        logo_widget = QWidget()
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(5)

        logo_icon = QLabel()
        logo_icon.setObjectName("HeaderLogoIcon")
        pixmap = QPixmap(str(resource_path("icons", "app.png")))
        if not pixmap.isNull():
            logo_icon.setPixmap(
                pixmap.scaled(
                    22, 22,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        logo_layout.addWidget(logo_icon)

        logo_text = QLabel("LeafVeins")
        logo_text.setObjectName("HeaderLogo")
        logo_layout.addWidget(logo_text)
        layout.addWidget(logo_widget)

        self.header_title = QLabel("Untitled Project")
        self.header_title.setObjectName("HeaderTitle")
        self.header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header_title, 1)

        header_buttons = (
            ("Layout  ⌄", self._show_layout_menu),
            ("?", self.show_shortcuts),
        )
        for text, handler in header_buttons:
            button = QToolButton()
            button.setText(text)
            button.setObjectName("HeaderActionButton")
            button.clicked.connect(handler)
            layout.addWidget(button)

        header.setStyleSheet(web_qss("""
            QFrame#OverleafHeader {
                background-color: $ol_header_bg;
                border-bottom: 1px solid $ol_header_border;
            }
            QLabel#HeaderLogoIcon {
                background-color: transparent;
                border: none;
            }
            QLabel#HeaderLogo {
                color: $ol_green_light;
                font-size: 13px;
                font-weight: 700;
                padding: 0 6px 0 0;
            }
            QLabel#HeaderTitle {
                color: $ol_header_fg;
                font-size: 13px;
                font-weight: 600;
            }
            QToolButton#HeaderMenuButton, QToolButton#HeaderActionButton {
                background-color: transparent;
                color: $ol_header_muted;
                border: none;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QToolButton#HeaderMenuButton:hover,
            QToolButton#HeaderActionButton:hover {
                background-color: $ol_header_hover;
                color: $ol_header_fg;
            }
        """))
        return header

    def _show_toast(self, message: str) -> None:
        """Show a short-lived toast in the bottom-right of the main window."""
        label = self.toast_label
        label.setText(message)
        label.adjustSize()
        central = self.centralWidget()
        x = max(10, central.width() - label.width() - 20)
        y = max(10, central.height() - label.height() - 20)
        label.move(x, y)
        label.raise_()
        label.setVisible(True)
        QTimer.singleShot(2600, label.hide)

    def _show_header_menu(self) -> None:
        """Show a compact project menu from the web-style header."""
        menu = QMenu(self)
        for text, handler in (
            ("New Project", self.new_project),
            ("Open Project", self.open_project),
            ("Save File", self.save_file),
            ("Close Current File", self.close_current_file),
            ("Compile", self.compile),
            ("Keyboard Shortcuts", self.show_shortcuts),
        ):
            menu.addAction(text, handler)
        button = self.sender()
        if isinstance(button, QToolButton):
            menu.exec(button.mapToGlobal(QPoint(0, button.height())))
        else:
            menu.exec(self.mapToGlobal(QPoint(20, 48)))

    def _show_layout_menu(self) -> None:
        """Show the workspace layout dropdown from the header."""
        menu = QMenu(self)
        menu.addAction("Editor & PDF", lambda: self._apply_web_layout("split"))
        menu.addAction("Editor Only", lambda: self._apply_web_layout("editor"))
        menu.addAction("PDF Only", lambda: self._apply_web_layout("pdf"))
        menu.addSeparator()
        menu.addAction("Toggle File Tree", self.toggle_file_tree)
        button = self.sender()
        if isinstance(button, QToolButton):
            menu.exec(button.mapToGlobal(QPoint(0, button.height())))
        else:
            menu.exec(self.mapToGlobal(QPoint(800, 48)))

    def _apply_web_layout(self, mode: str) -> None:
        """Apply one of the reference HTML workspace layouts."""
        self.editor.setVisible(mode != "pdf")
        self.pdf_viewer.setVisible(mode != "editor")
        if mode == "editor":
            self.file_tree.setVisible(True)
        elif mode == "pdf":
            self.file_tree.setVisible(False)
        else:
            self.file_tree.setVisible(True)
        self._show_toast(f"Layout: {mode}")

    def _setup_menu(self) -> None:
        """Set up menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_action = file_menu.addAction("&New Project...")
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_project)
        
        open_action = file_menu.addAction("&Open Project...")
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_project)
        
        file_menu.addSeparator()
        
        save_action = file_menu.addAction("&Save")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_file)
        
        save_as_action = file_menu.addAction("Save &As...")
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        
        close_file_action = file_menu.addAction("Close &Current File")
        close_file_action.setShortcut(QKeySequence("Ctrl+W"))
        close_file_action.triggered.connect(self.close_current_file)
        
        file_menu.addSeparator()
        
        close_action = file_menu.addAction("&Close Project")
        close_action.triggered.connect(self.close_project)
        
        file_menu.addSeparator()
        
        # Recent projects submenu
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._update_recent_menu()
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = edit_menu.addAction("&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.editor.editor.undo)
        
        redo_action = edit_menu.addAction("&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.editor.editor.redo)
        
        edit_menu.addSeparator()
        
        cut_action = edit_menu.addAction("Cu&t")
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.triggered.connect(self.editor.editor.cut)
        
        copy_action = edit_menu.addAction("&Copy")
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.editor.editor.copy)
        
        paste_action = edit_menu.addAction("&Paste")
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self.editor.editor.paste)
        
        edit_menu.addSeparator()
        
        find_action = edit_menu.addAction("&Find...")
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.show_find_dialog)
        
        replace_action = edit_menu.addAction("&Replace...")
        replace_action.setShortcut(QKeySequence.StandardKey.Replace)
        replace_action.triggered.connect(self.show_replace_dialog)
        
        goto_action = edit_menu.addAction("&Go to Line...")
        goto_action.setShortcut(QKeySequence("Ctrl+G"))
        goto_action.triggered.connect(self.show_goto_dialog)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        self.toggle_file_tree_action = view_menu.addAction("File Tree")
        self.toggle_file_tree_action.setCheckable(True)
        self.toggle_file_tree_action.setChecked(True)
        self.toggle_file_tree_action.triggered.connect(self.toggle_file_tree)
        
        self.toggle_preview_action = view_menu.addAction("PDF Preview")
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(True)
        self.toggle_preview_action.triggered.connect(self.toggle_preview)
        
        self.toggle_console_action = view_menu.addAction("Console")
        self.toggle_console_action.setCheckable(True)
        self.toggle_console_action.triggered.connect(self.toggle_console)
        
        view_menu.addSeparator()
        
        theme_menu = view_menu.addMenu("Theme")
        self.theme_dark_action = theme_menu.addAction("Dark")
        self.theme_dark_action.setCheckable(True)
        self.theme_dark_action.triggered.connect(lambda: self.set_theme("dark"))
        self.theme_light_action = theme_menu.addAction("Light")
        self.theme_light_action.setCheckable(True)
        self.theme_light_action.triggered.connect(lambda: self.set_theme("light"))
        self.theme_system_action = theme_menu.addAction("System")
        self.theme_system_action.setCheckable(True)
        self.theme_system_action.triggered.connect(lambda: self.set_theme("system"))

        self.theme_overleaf_action = theme_menu.addAction("Overleaf")
        self.theme_overleaf_action.setCheckable(True)
        self.theme_overleaf_action.triggered.connect(lambda: self.set_theme("overleaf"))
        
        # Project menu
        project_menu = menubar.addMenu("&Project")
        
        new_file_action = project_menu.addAction("New File")
        new_file_action.setShortcut(QKeySequence("Ctrl+N"))
        new_file_action.triggered.connect(self.new_file)
        
        set_main_action = project_menu.addAction("Set as Main File")
        set_main_action.triggered.connect(self.set_main_file)
        
        project_menu.addSeparator()
        
        project_settings_action = project_menu.addAction("Project Settings...")
        project_settings_action.triggered.connect(self.show_project_settings)
        
        # Compile menu
        compile_menu = menubar.addMenu("&Compile")
        
        compile_action = compile_menu.addAction("Compile (F5)")
        compile_action.setShortcut(QKeySequence("F5"))
        compile_action.triggered.connect(self.compile)
        
        compile_menu.addSeparator()
        
        self.compiler_menu = compile_menu.addMenu("Compiler")
        self._update_compiler_menu()
        
        compile_menu.addSeparator()
        
        stop_action = compile_menu.addAction("Stop Compilation")
        stop_action.setShortcut(QKeySequence("Ctrl+."))
        stop_action.triggered.connect(self.stop_compilation)
        
        clean_action = compile_menu.addAction("Clean Build Files")
        clean_action.triggered.connect(self.clean_build)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = help_menu.addAction("&About LeafVeins")
        about_action.triggered.connect(self.show_about)
        
        help_menu.addSeparator()
        
        docs_action = help_menu.addAction("Documentation")
        docs_action.triggered.connect(self.show_docs)
        
        shortcuts_action = help_menu.addAction("Keyboard Shortcuts")
        shortcuts_action.triggered.connect(self.show_shortcuts)
    
    def _setup_toolbar(self) -> None:
        """Set up main toolbar."""
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)
        
        # Project actions
        self.toolbar.addAction("New Project", self.new_project)
        self.toolbar.addAction("Open Project", self.open_project)
        self.toolbar.addAction("Save", self.save_file)
        self.toolbar.addSeparator()
        
        # Compile
        self.compile_btn = self.toolbar.addAction("Compile")
        self.compile_btn.setObjectName("CompileButton")
        self.compile_btn.setToolTip("Compile (F5)")
        self.compile_btn.triggered.connect(self.compile)
        
        self.stop_btn = self.toolbar.addAction("Stop")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setToolTip("Stop Compilation (Ctrl+.)")
        self.stop_btn.triggered.connect(self.stop_compilation)
        self.stop_btn.setEnabled(False)
        
        self.toolbar.addSeparator()
        
        # Compiler selector
        self.compiler_combo = QComboBox()
        self.compiler_combo.addItems(["pdflatex", "xelatex", "lualatex"])
        self.compiler_combo.currentTextChanged.connect(self.on_compiler_changed)
        self.toolbar.addWidget(self.compiler_combo)
        
        self.toolbar.addSeparator()
        
        # Navigation
        self.toolbar.addAction("Previous Page", self.pdf_viewer.prev_page)
        self.toolbar.addAction("Next Page", self.pdf_viewer.next_page)
        
        self.toolbar.addSeparator()
        
        # Zoom
        self.toolbar.addAction("Zoom In", self.pdf_viewer.zoom_in)
        self.toolbar.addAction("Zoom Out", self.pdf_viewer.zoom_out)
        self.toolbar.addAction("Fit Width", self.pdf_viewer.fit_width)
    
    def _setup_statusbar(self) -> None:
        """Set up status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # Permanent widgets
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label)
        
        self.statusbar.addPermanentWidget(QLabel(" | "))
        
        self.line_col_label = QLabel("Ln 1, Col 1")
        self.statusbar.addPermanentWidget(self.line_col_label)
        
        self.statusbar.addPermanentWidget(QLabel(" | "))
        
        self.encoding_label = QLabel("UTF-8")
        self.statusbar.addPermanentWidget(self.encoding_label)
        
        self.statusbar.addPermanentWidget(QLabel(" | "))
        
        self.eol_label = QLabel("LF")
        self.statusbar.addPermanentWidget(self.eol_label)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.statusbar.addPermanentWidget(self.progress_bar)
    
    def _setup_shortcuts(self) -> None:
        """Set up additional keyboard shortcuts."""
        # Toggle panels
        self.shortcut_file_tree = QAction(self)
        self.shortcut_file_tree.setShortcut(QKeySequence("Ctrl+1"))
        self.shortcut_file_tree.triggered.connect(self.toggle_file_tree)
        self.addAction(self.shortcut_file_tree)
        
        self.shortcut_preview = QAction(self)
        self.shortcut_preview.setShortcut(QKeySequence("Ctrl+2"))
        self.shortcut_preview.triggered.connect(self.toggle_preview)
        self.addAction(self.shortcut_preview)
        
        self.shortcut_console = QAction(self)
        self.shortcut_console.setShortcut(QKeySequence("Ctrl+3"))
        self.shortcut_console.triggered.connect(self.toggle_console)
        self.addAction(self.shortcut_console)
        
        # Compile
        self.shortcut_compile = QAction(self)
        self.shortcut_compile.setShortcut(QKeySequence("F5"))
        self.shortcut_compile.triggered.connect(self.compile)
        self.addAction(self.shortcut_compile)

        # SyncTeX forward search
        self.shortcut_forward_search = QShortcut(QKeySequence("Ctrl+Alt+J"), self)
        self.shortcut_forward_search.activated.connect(self.on_forward_search)
    
    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # File tree
        self.file_tree.file_opened.connect(self.open_file)
        self.file_tree.file_created.connect(self.on_file_created)
        self.file_tree.file_deleted.connect(self.on_file_deleted)
        self.file_tree.file_renamed.connect(self.on_file_renamed)
        self.file_tree.compile_requested.connect(self.compile)
        self.file_tree.project_changed.connect(self.on_project_changed)
        
        # Editor
        self.editor.file_modified.connect(self.on_file_modified)
        self.editor.cursor_position_changed.connect(self.on_cursor_position_changed)
        self.editor.compile_requested.connect(self.compile)
        self.editor.forward_search_requested.connect(self.on_forward_search)
        self.editor.outline_changed.connect(self.file_tree.set_outline)
        
        # File outline navigation
        self.file_tree.outline_item_clicked.connect(self.on_outline_item_clicked)
        
        # PDF viewer
        self.pdf_viewer.page_changed.connect(self.on_page_changed)
        self.pdf_viewer.inverse_search_requested.connect(self.on_inverse_search)
        self.pdf_viewer.forward_search_requested.connect(self.on_forward_search)
        self.pdf_viewer.compile_requested.connect(self.compile)
        self.pdf_viewer.logs_requested.connect(self.toggle_console)
        
        # Compiler
        self.compiler_manager.compilation_started.connect(self.on_compilation_started)
        self.compiler_manager.compilation_finished.connect(self.on_compilation_finished)
        self.compiler_manager.compilation_progress.connect(self.on_compilation_progress)
        
        # Log widget
        self.log_widget.error_clicked.connect(self.on_error_clicked)
    
    def _apply_theme(self) -> None:
        """Apply the current theme."""
        theme = self.config.get('ui.theme', 'dark')
        self.set_theme(theme)
    
    def set_theme(self, theme: str) -> None:
        """Change application theme."""
        self.config.set('ui.theme', theme)
        palette = get_palette(theme)

        is_web = palette.name == "overleaf"

        # Update menu checks
        self.theme_dark_action.setChecked(theme == "dark")
        self.theme_light_action.setChecked(theme == "light")
        self.theme_system_action.setChecked(theme == "system")
        self.theme_overleaf_action.setChecked(is_web)

        # The web style replaces the classic menu bar and main toolbar with the
        # custom header, but leaves every action available through the menu.
        self.overleaf_header.setVisible(is_web)
        self.menuBar().setVisible(not is_web)
        self.toolbar.setVisible(not is_web)

        # Apply to children first so their own stylesheets take precedence.
        for widget in (self.editor, self.file_tree, self.pdf_viewer, self.log_widget):
            widget.set_theme(theme)

        stylesheet = qss(self._main_stylesheet(), palette)
        if is_web:
            stylesheet += qss(self._overleaf_button_stylesheet(), palette)
            stylesheet += web_qss("""
                QSplitter::handle {
                    background-color: $ol_border;
                    width: 5px;
                }
                QSplitter::handle:hover {
                    background-color: $ol_green;
                }
                QLabel#OverleafToast {
                    background-color: rgba(30, 37, 48, 230);
                    color: white;
                    border-radius: 14px;
                    padding: 6px 14px;
                    font-size: 11px;
                }
            """)
        self.setStyleSheet(stylesheet)

    @staticmethod
    def _main_stylesheet() -> str:
        """Shared QSS template for every theme."""
        return """
            QMainWindow {
                background-color: $window_bg;
                color: $window_fg;
            }
            QMenuBar {
                background-color: $menubar_bg;
                color: $menubar_fg;
                border: none;
            }
            QMenuBar::item:selected {
                background-color: $menubar_selected_bg;
                color: $menu_selected_fg;
            }
            QMenu {
                background-color: $menu_bg;
                color: $menu_fg;
                border: 1px solid $menu_border;
            }
            QMenu::item:selected {
                background-color: $menu_selected_bg;
                color: $menu_selected_fg;
            }
            QToolBar {
                background-color: $toolbar_bg;
                border: $toolbar_border;
                spacing: 4px;
            }
            QToolButton {
                background-color: transparent;
                color: $foreground;
                border: none;
                padding: 4px;
                border-radius: 3px;
            }
            QToolButton:hover {
                background-color: $toolbar_button_hover;
            }
            QToolButton:pressed {
                background-color: $toolbar_button_pressed;
            }
            QStatusBar {
                background-color: $status_bg;
                color: $status_fg;
                border-top: 1px solid $status_border;
            }
            QDockWidget {
                background-color: $dock_bg;
                color: $window_fg;
                titlebar-close-icon: url(close.png);
                titlebar-normal-icon: url(undock.png);
            }
            QDockWidget::title {
                background-color: $dock_title_bg;
                color: $dock_title_fg;
                padding: 4px;
            }
            QSplitter::handle {
                background-color: $splitter_bg;
            }
            QComboBox, QSpinBox, QLineEdit {
                background-color: $input_bg;
                color: $input_fg;
                border: 1px solid $input_border;
                padding: 2px 8px;
                border-radius: 3px;
            }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
                border: 1px solid $input_focus_border;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: $combo_bg;
                color: $combo_fg;
                selection-background-color: $combo_item_selected_bg;
                selection-color: $combo_item_selected_fg;
                border: 1px solid $combo_border;
            }
            QProgressBar {
                background-color: $window_bg;
                border: 1px solid $input_border;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: $progress_bg;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: $scroll_shadow;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: $scroll_thumb;
                border-radius: 3px;
                min-height: 8px;
                min-width: 8px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background-color: $scroll_thumb_hover;
            }
            QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {
                background-color: $scroll_thumb_active;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                border: none;
                background: transparent;
            }
        """

    @staticmethod
    def _overleaf_button_stylesheet() -> str:
        """Give the primary compile action the theme's green button treatment."""
        return """
            QToolButton#CompileButton {
                background-color: $button_bg;
                color: $button_fg;
                border: none;
                padding: 5px 12px;
                border-radius: 3px;
                font-weight: bold;
            }
            QToolButton#CompileButton:hover { background-color: $button_hover; }
            QToolButton#CompileButton:pressed { background-color: $button_pressed; }
            QToolButton#CompileButton:disabled {
                background-color: $button_disabled_bg;
                color: $button_disabled_fg;
            }
            QToolButton#StopButton {
                background-color: $button_secondary_bg;
                color: $button_secondary_fg;
                border: none;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QToolButton#StopButton:hover { background-color: $button_hover; }
            QToolButton#StopButton:disabled {
                background-color: $button_disabled_bg;
                color: $button_disabled_fg;
            }
        """
    
    def _restore_settings(self) -> None:
        """Restore window geometry and state."""
        geometry = self.config.get('ui.window_geometry')
        if geometry:
            try:
                from PyQt6.QtCore import QByteArray
                geom_bytes = QByteArray.fromHex(geometry.encode('utf-8'))
                self.restoreGeometry(geom_bytes)
            except Exception:
                pass
        
        if self.config.get('ui.maximized', False):
            self.showMaximized()
        
        # Restore splitter sizes
        file_tree_width = self.config.get('ui.file_tree_width', 250)
        preview_width = self.config.get('ui.preview_width', 400)
        console_height = self.config.get('ui.console_height', 200)
        
        self.main_splitter.setSizes([file_tree_width, self.width() - file_tree_width])
        self.center_splitter.setSizes([self.width() - preview_width, preview_width])
        self.console_dock.setMinimumHeight(console_height)
        
        # Restore visibility
        self.toggle_file_tree_action.setChecked(self.config.get('ui.show_file_tree', True))
        self.toggle_preview_action.setChecked(self.config.get('ui.show_preview', True))
        self.toggle_console_action.setChecked(self.config.get('ui.show_console', False))
        
        self.file_tree.setVisible(self.config.get('ui.show_file_tree', True))
        self.pdf_viewer.setVisible(self.config.get('ui.show_preview', True))
        self.console_dock.setVisible(self.config.get('ui.show_console', False))
    
    def _save_settings(self) -> None:
        """Save window geometry and state."""
        self.config.set('ui.window_geometry', self.saveGeometry().toHex().data().decode())
        self.config.set('ui.maximized', self.isMaximized())
        self.config.set('ui.file_tree_width', self.main_splitter.sizes()[0])
        self.config.set('ui.preview_width', self.center_splitter.sizes()[1])
        self.config.set('ui.console_height', self.console_dock.height())
        self.config.set('ui.show_file_tree', self.file_tree.isVisible())
        self.config.set('ui.show_preview', self.pdf_viewer.isVisible())
        self.config.set('ui.show_console', self.console_dock.isVisible())
    
    def _update_recent_menu(self) -> None:
        """Update recent projects menu."""
        self.recent_menu.clear()
        
        recent = self.project_manager.list_recent_projects(10)
        for project in recent:
            action = self.recent_menu.addAction(project.name)
            action.setData(project.path)
            action.triggered.connect(lambda checked, p=project.path: self.open_project_path(p))
        
        if not recent:
            action = self.recent_menu.addAction("(No recent projects)")
            action.setEnabled(False)
    
    def _update_compiler_menu(self) -> None:
        """Update compiler menu."""
        self.compiler_menu.clear()
        
        compilers = ["pdflatex", "xelatex", "lualatex"]
        current = self.project_manager.get_current_project()
        current_compiler = current.compiler if current else "pdflatex"
        
        for compiler in compilers:
            action = self.compiler_menu.addAction(compiler)
            action.setCheckable(True)
            action.setChecked(compiler == current_compiler)
            action.triggered.connect(lambda checked, c=compiler: self.set_compiler(c))
        
        self.compiler_combo.setCurrentText(current_compiler)
    
    def _show_welcome(self) -> None:
        """Show welcome screen or restore last project."""
        recent = self.project_manager.list_recent_projects(1)
        if recent:
            # Open last project
            self.open_project_path(recent[0].path)
        else:
            # Skip welcome text for now to avoid crash
            pass
    
    # Menu actions
    def new_project(self) -> None:
        """Create a new project."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("New Project")
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        
        name_edit = QLineEdit()
        form.addRow("Project Name:", name_edit)
        
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("Select directory...")
        browse_btn = QWidget()
        browse_layout = QHBoxLayout(browse_btn)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.addWidget(path_edit)
        
        def browse():
            dir_path = QFileDialog.getExistingDirectory(self, "Select Project Directory")
            if dir_path:
                path_edit.setText(dir_path)
        
        browse_action = QAction("Browse", self)
        browse_action.triggered.connect(browse)
        # Add button to layout
        from PyQt6.QtWidgets import QPushButton
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(browse)
        browse_layout.addWidget(browse_button)
        
        form.addRow("Location:", browse_btn)
        
        template_combo = QComboBox()
        templates = self.project_manager.get_templates()
        for tmpl in templates:
            template_combo.addItem(tmpl['name'], tmpl['name'])
        form.addRow("Template:", template_combo)
        
        compiler_combo = QComboBox()
        compiler_combo.addItems(["pdflatex", "xelatex", "lualatex"])
        form.addRow("Compiler:", compiler_combo)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            path = Path(path_edit.text().strip()) / name
            template = template_combo.currentData()
            compiler = compiler_combo.currentText()
            
            if name and path:
                project = self.project_manager.create_project(name, path, template, compiler=compiler)
                if project:
                    self.open_project_path(str(path))
    
    def open_project(self) -> None:
        """Open an existing project."""
        dir_path = QFileDialog.getExistingDirectory(self, "Open Project")
        if dir_path:
            self.open_project_path(dir_path)
    
    def open_project_path(self, path: str) -> None:
        """Open project at given path."""
        project = self.project_manager.open_project(Path(path))
        if project:
            self.current_file_path = None
            self.file_tree.set_project_root(project.path)
            
            # Open main file
            main_file = Path(project.path) / project.main_file
            if main_file.exists():
                self.open_file(str(main_file))
            
            self._update_compiler_menu()
            self._update_recent_menu()
            self.setWindowTitle(f"LeafVeins - {project.name}")
            self.status_label.setText(f"Project: {project.name}")
    
    def close_project(self) -> None:
        """Close current project."""
        self.project_manager.close_project()
        self.file_tree.set_project_root("")
        self.editor.editor.clear()
        self.pdf_viewer.load_pdf("")  # Clear PDF
        self.current_file_path = None
        self.setWindowTitle("LeafVeins - LaTeX Editor")
        self.status_label.setText("No project open")
    
    def save_file(self) -> None:
        """Save current file."""
        if self.current_file_path:
            self.editor.save_file(self.current_file_path)
        else:
            self.save_file_as()
    
    def save_file_as(self) -> None:
        """Save current file with new name."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save File", "", "LaTeX Files (*.tex);;All Files (*)"
        )
        if file_path:
            self.editor.save_file(file_path)
            self.current_file_path = file_path
    
    def close_current_file(self) -> None:
        """Close the active editor tab."""
        self.editor.close_current_file()
        path = self.editor.get_current_file_path()
        self.current_file_path = path
        self.status_label.setText(
            f"Editing: {Path(path).name}" if path else "No file open"
        )
    
    def new_file(self) -> None:
        """Create a new file in the current project."""
        project = self.project_manager.get_current_project()
        if not project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        name, ok = QInputDialog.getText(self, "New File", "File name:", text="new.tex")
        if ok and name:
            file_path = Path(project.path) / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
            self.open_file(str(file_path))
    
    def open_file(self, file_path: str) -> None:
        """Open a file in the editor."""
        if self.editor.load_file(file_path):
            self.current_file_path = file_path
            self.status_label.setText(f"Editing: {Path(file_path).name}")
            
            # Add to recent files
            project = self.project_manager.get_current_project()
            if project:
                self.db.add_recent_file(project.id, file_path)
    
    def compile(self) -> None:
        """Compile the current project."""
        project = self.project_manager.get_current_project()
        if not project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        
        if self.is_compiling:
            return
        
        main_file = project.main_file
        main_path = Path(project.path) / main_file
        if not main_path.exists():
            QMessageBox.warning(self, "Main File Not Found", 
                              f"Main file '{main_file}' does not exist.")
            return
        
        # Save current file if modified
        if self.editor.editor.is_modified:
            self.editor.save_file()
        
        # Clear log
        self.log_widget.clear()
        self.console_dock.show()
        self.console_dock.raise_()
        
        # Get compiler options
        options = {
            'timeout': self.config.get('compiler.timeout', 60),
            'max_passes': self.config.get('compiler.max_passes', 5),
            'bibtex_enabled': self.config.get('compiler.bibtex_enabled', True),
            'makeindex_enabled': self.config.get('compiler.makeindex_enabled', True),
            'shell_escape': self.config.get('compiler.shell_escape', False),
            'synctex': self.config.get('compiler.synctex', True),
            'output_dir': 'build',
        }
        
        # Start compilation
        self.is_compiling = True
        self.compile_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText("Compiling...")
        
        self.compiler_manager.compile(
            Path(project.path), main_file, project.compiler, options
        )
    
    def stop_compilation(self) -> None:
        """Stop current compilation."""
        self.compiler_manager.cancel()
    
    def clean_build(self) -> None:
        """Clean build directory."""
        project = self.project_manager.get_current_project()
        if not project:
            return
        
        build_dir = Path(project.path) / 'build'
        if build_dir.exists():
            import shutil
            shutil.rmtree(build_dir)
            self.log_widget.append("Build directory cleaned.\n", "info")
    
    def on_compiler_changed(self, compiler: str) -> None:
        """Handle compiler change from toolbar."""
        self.set_compiler(compiler)
    
    def set_compiler(self, compiler: str) -> None:
        """Set compiler for current project."""
        project = self.project_manager.get_current_project()
        if project:
            self.project_manager.set_compiler(project.id, compiler)
            self._update_compiler_menu()
    
    def show_find_dialog(self) -> None:
        """Show find dialog."""
        # Would implement find/replace dialog
        pass
    
    def show_replace_dialog(self) -> None:
        """Show replace dialog."""
        pass
    
    def show_goto_dialog(self) -> None:
        """Show go to line dialog."""
        line, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", 1, 1, 1000000)
        if ok:
            self.editor.goto_line(line)
    
    def show_project_settings(self) -> None:
        """Show project settings dialog."""
        pass
    
    def show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(self, "About LeafVeins",
            "LeafVeins - LaTeX Editor\n\n"
            "A standalone Windows application for LaTeX document writing and typesetting.\n\n"
            "Version 1.0.0\n"
            "Built with PyQt6"
        )
    
    def show_docs(self) -> None:
        """Show documentation."""
        import webbrowser
        webbrowser.open("https://github.com/ayaka-notes/leafveins")
    
    def set_main_file(self) -> None:
        """Set current file as main file."""
        if self.current_file_path:
            project = self.project_manager.get_current_project()
            if project:
                rel_path = Path(self.current_file_path).relative_to(project.path)
                self.project_manager.set_main_file(project.id, str(rel_path))
                self.status_label.setText(f"Main file set to: {rel_path}")
    
    def show_shortcuts(self) -> None:
        """Show keyboard shortcuts."""
        shortcuts = """
        <h3>Keyboard Shortcuts</h3>
        <table>
        <tr><td><b>Ctrl+N</b></td><td>New File</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open Project</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>Save</td></tr>
        <tr><td><b>Ctrl+Shift+S</b></td><td>Save As</td></tr>
        <tr><td><b>Ctrl+W</b></td><td>Close Current File</td></tr>
        <tr><td><b>F5</b></td><td>Compile</td></tr>
        <tr><td><b>Ctrl+.</b></td><td>Stop Compilation</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>Find</td></tr>
        <tr><td><b>Ctrl+H</b></td><td>Replace</td></tr>
        <tr><td><b>Ctrl+G</b></td><td>Go to Line</td></tr>
        <tr><td><b>Ctrl+/</b></td><td>Toggle Comment</td></tr>
        <tr><td><b>Ctrl+B</b></td><td>Bold selection</td></tr>
        <tr><td><b>Ctrl+I</b></td><td>Italic selection</td></tr>
        <tr><td><b>Ctrl+Alt+J</b></td><td>Jump from editor to PDF (SyncTeX)</td></tr>
        <tr><td><b>Ctrl+Click</b></td><td>Jump from PDF to editor (SyncTeX)</td></tr>
        <tr><td><b>Ctrl+1</b></td><td>Toggle File Tree</td></tr>
        <tr><td><b>Ctrl+2</b></td><td>Toggle PDF Preview</td></tr>
        <tr><td><b>Ctrl+3</b></td><td>Toggle Console</td></tr>
        </table>
        """
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)
    
    def toggle_file_tree(self) -> None:
        """Toggle file tree visibility."""
        visible = not self.file_tree.isVisible()
        self.file_tree.setVisible(visible)
        self.toggle_file_tree_action.setChecked(visible)
    
    def toggle_preview(self) -> None:
        """Toggle PDF preview visibility."""
        visible = not self.pdf_viewer.isVisible()
        self.pdf_viewer.setVisible(visible)
        self.toggle_preview_action.setChecked(visible)
    
    def toggle_console(self) -> None:
        """Toggle console visibility."""
        visible = not self.console_dock.isVisible()
        self.console_dock.setVisible(visible)
        self.toggle_console_action.setChecked(visible)
    
    # Signal handlers
    def on_file_created(self, file_path: str) -> None:
        """Handle file creation."""
        self.open_file(file_path)
    
    def on_file_deleted(self, file_path: str) -> None:
        """Handle file deletion."""
        if self.current_file_path == file_path:
            self.editor.editor.clear()
            self.current_file_path = None
    
    def on_file_renamed(self, old_path: str, new_path: str) -> None:
        """Handle file rename."""
        if self.current_file_path == old_path:
            self.current_file_path = new_path
            self.editor.editor.current_file_path = new_path
    
    def on_file_modified(self, modified: bool) -> None:
        """Handle file modification status."""
        if modified:
            self.setWindowTitle(f"LeafVeins - {self.project_manager.get_current_project().name} *")
        else:
            self.setWindowTitle(f"LeafVeins - {self.project_manager.get_current_project().name}")
    
    def on_cursor_position_changed(self, line: int, column: int) -> None:
        """Handle cursor position change."""
        self.line_col_label.setText(f"Ln {line}, Col {column}")
    
    def on_page_changed(self, page: int) -> None:
        """Handle PDF page change."""
        pass
    
    def on_outline_item_clicked(self, line: int) -> None:
        """Jump the editor to a section selected in the file outline."""
        self.editor.goto_line(line, 1)
        self.editor.setFocus()

    def on_forward_search(self, line: Optional[int] = None,
                          column: Optional[int] = None) -> None:
        """Jump from the editor cursor to the corresponding PDF position."""
        project = self.project_manager.get_current_project()
        if not project:
            self.statusbar.showMessage("Open a project before using SyncTeX", 4000)
            return

        if line is None:
            line = self.editor.get_current_line()
        if column is None:
            column = self.editor.get_current_column()

        project_dir = Path(project.path)
        current_file = self.editor.get_current_file_path()
        if current_file and Path(current_file).suffix.lower() == '.tex':
            input_file = Path(current_file)
        else:
            input_file = project_dir / project.main_file

        self.statusbar.showMessage("Searching PDF position...", 2000)
        try:
            result = self.compiler_manager.sync_from_code(
                project_dir, str(input_file), line, column
            )
            positions = result.get('code_positions', [])
            if not positions:
                self.statusbar.showMessage("No PDF position found for this line", 4000)
                return

            pos = positions[0]
            page = max(1, int(pos.get('page', 1))) - 1
            self.pdf_viewer.go_to_page(page)

            x = float(pos.get('x', pos.get('h', 0)))
            y = float(pos.get('y', pos.get('v', 0)))
            width = float(pos.get('W', 200))
            height = float(pos.get('H', 12))
            rect = QRect(int(x), int(y - height), int(width), int(height))
            self.pdf_viewer.highlight_position(page + 1, rect)
            self.statusbar.showMessage(f"Synced to PDF page {page + 1}", 3000)
        except Exception as e:
            self.statusbar.showMessage(f"Forward search failed: {e}", 6000)
            self.log_widget.append(f"Forward SyncTeX failed: {e}\n", "error")
    
    def on_inverse_search(self, page: int, pos: QPoint) -> None:
        """Jump from a PDF position to the corresponding editor location."""
        project = self.project_manager.get_current_project()
        if not project:
            self.statusbar.showMessage("Open a project before using SyncTeX", 4000)
            return

        project_dir = Path(project.path)
        self.statusbar.showMessage("Searching source position...", 2000)
        try:
            result = self.compiler_manager.sync_from_pdf(
                project_dir, page, float(pos.x()), float(pos.y())
            )
            positions = result.get('pdf_positions', [])
            if not positions:
                self.statusbar.showMessage("No source position found here", 4000)
                return

            entry = positions[0]
            file_path = Path(entry['file'])
            if not file_path.exists():
                candidate = project_dir / 'build' / file_path.name
                if candidate.exists():
                    file_path = candidate
            line = max(1, int(entry.get('line', 1)))
            column = max(1, int(entry.get('column', 1)))

            current_file = self.editor.get_current_file_path()
            if not current_file or Path(current_file).resolve() != file_path.resolve():
                self.open_file(str(file_path))
            self.editor.goto_line(line, column)
            self.editor.editor.setFocus()
            self.statusbar.showMessage(
                f"Synced to {file_path.name}:{line}", 3000
            )
        except Exception as e:
            self.statusbar.showMessage(f"Inverse search failed: {e}", 6000)
            self.log_widget.append(f"Inverse SyncTeX failed: {e}\n", "error")
    
    def on_compilation_started(self) -> None:
        """Handle compilation start."""
        self.log_widget.append("=== Compilation Started ===\n", "info")
    
    def on_compilation_finished(self, result: CompilationResult) -> None:
        """Handle compilation finish."""
        self.is_compiling = False
        self.compile_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        project = self.project_manager.get_current_project()
        
        if result.status == CompilationStatus.SUCCESS:
            self.log_widget.append("\n=== Compilation Successful ===\n", "success")
            self.status_label.setText("Compilation successful")
            
            # Load PDF
            pdf_files = [f for f in result.output_files if f.endswith('.pdf')]
            if pdf_files:
                self.pdf_viewer.load_pdf(pdf_files[0])
            
            # Record in history
            if project:
                self.project_manager.add_compilation_record(
                    project.id, project.compiler, "success",
                    result.log, result.output_files, result.duration_ms
                )
        
        elif result.status == CompilationStatus.ERROR:
            self.log_widget.append(f"\n=== Compilation Failed ===\n{result.error_message}\n", "error")
            self.status_label.setText("Compilation failed")
            
            if project:
                self.project_manager.add_compilation_record(
                    project.id, project.compiler, "error",
                    result.log, result.output_files, result.duration_ms
                )
        
        elif result.status == CompilationStatus.TIMEOUT:
            self.log_widget.append("\n=== Compilation Timed Out ===\n", "error")
            self.status_label.setText("Compilation timed out")
        
        elif result.status == CompilationStatus.CANCELLED:
            self.log_widget.append("\n=== Compilation Cancelled ===\n", "warning")
            self.status_label.setText("Compilation cancelled")
    
    def on_compilation_progress(self, line: str) -> None:
        """Handle compilation progress output."""
        self.log_widget.append_log(line)
    
    def on_error_clicked(self, file_path: str, line: int) -> None:
        """Handle error click in log."""
        self.open_file(file_path)
        self.editor.goto_line(line)
    
    def on_project_changed(self, path: str) -> None:
        """Handle project change."""
        self._update_compiler_menu()
    
    def closeEvent(self, event) -> None:
        """Handle window close."""
        self._save_settings()
        
        # Stop compilation if running
        if self.is_compiling:
            self.compiler_manager.cancel()
        
        event.accept()


def main():
    """Application entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="LeafVeins - LaTeX Editor")
    parser.add_argument('--screenshot', type=str, help='Take screenshot and exit')
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    app.setApplicationName("LeafVeins")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AyakaLeaf")
    icon_path = resource_path("icons", "app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Set application font
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    window = MainWindow()
    
    if args.screenshot:
        # Take screenshot after window is shown
        def take_screenshot():
            # Grab the window
            pixmap = window.grab()
            pixmap.save(args.screenshot)
            print(f"Screenshot saved to {args.screenshot}")
            app.quit()
        
        QTimer.singleShot(1000, take_screenshot)
        window.show()
    else:
        window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
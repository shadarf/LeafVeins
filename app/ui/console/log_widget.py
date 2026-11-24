"""Compilation log/console widget."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QToolBar, QComboBox,
    QCheckBox, QLabel, QMenu
)
from PyQt6.QtGui import QTextCharFormat, QFont, QTextCursor, QAction
from PyQt6.QtCore import Qt, pyqtSignal

from core.themes import get_palette, qss, qcolor, web_qss


class LogWidget(QWidget):
    """Widget for displaying compilation logs with error highlighting."""
    
    # Signals
    error_clicked = pyqtSignal(str, int)  # file_path, line_number
    clear_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_lines = 1000
        self.auto_scroll = True
        self.theme = "dark"
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setObjectName("LogToolbar")
        
        self.clear_action = self.toolbar.addAction("Clear")
        self.clear_action.triggered.connect(self.clear)
        
        self.toolbar.addSeparator()
        
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.toggled.connect(self._set_auto_scroll)
        self.toolbar.addWidget(self.auto_scroll_check)
        
        self.wrap_check = QCheckBox("Wrap lines")
        self.wrap_check.toggled.connect(self._set_wrap)
        self.toolbar.addWidget(self.wrap_check)
        
        self.toolbar.addSeparator()
        
        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("LogFilter")
        self.filter_combo.addItems(["All", "Errors", "Warnings", "Info"])
        self.filter_combo.currentTextChanged.connect(self._filter_changed)
        self.toolbar.addWidget(self.filter_combo)
        
        layout.addWidget(self.toolbar)
        
        # Log display
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(self.max_lines)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        # Monospace font
        font = QFont("Consolas", 9)
        font.setFixedPitch(True)
        self.log_view.setFont(font)
        
        # Context menu
        self.log_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_view.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.log_view)
        
        # Error highlighting formats (colours follow the active theme)
        self.error_format = QTextCharFormat()
        self.error_format.setFontWeight(QFont.Weight.Bold)
        self.warning_format = QTextCharFormat()
        self.info_format = QTextCharFormat()
        self.success_format = QTextCharFormat()
        self.success_format.setFontWeight(QFont.Weight.Bold)
        self.file_format = QTextCharFormat()
        self.file_format.setFontUnderline(True)
        self._apply_level_formats(get_palette(self.theme))

    def _apply_level_formats(self, palette) -> None:
        """Update log level colours from a theme palette."""
        self.error_format.setForeground(qcolor(palette.log_error))
        self.warning_format.setForeground(qcolor(palette.log_warning))
        self.info_format.setForeground(qcolor(palette.log_info))
        self.success_format.setForeground(qcolor(palette.log_success))
        self.file_format.setForeground(qcolor(palette.log_file))
    
    def append(self, text: str, level: str = "info") -> None:
        """Append text to the log."""
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Apply formatting based on level
        if level == "error":
            cursor.setCharFormat(self.error_format)
        elif level == "warning":
            cursor.setCharFormat(self.warning_format)
        elif level == "success":
            cursor.setCharFormat(self.success_format)
        elif level == "info":
            cursor.setCharFormat(self.info_format)
        else:
            cursor.setCharFormat(self.info_format)
        
        cursor.insertText(text)
        
        # Ensure we don't exceed max lines
        if self.log_view.blockCount() > self.max_lines:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.KeepAnchor,
                self.log_view.blockCount() - self.max_lines
            )
            cursor.removeSelectedText()
        
        # Auto-scroll
        if self.auto_scroll:
            self.log_view.ensureCursorVisible()
    
    def append_log(self, log: str) -> None:
        """Append log with automatic level detection."""
        lines = log.split('\n')
        for line in lines:
            level = self._detect_level(line)
            self.append(line + '\n', level)
    
    def _detect_level(self, line: str) -> str:
        """Detect log level from line content."""
        line_lower = line.lower()
        
        if any(kw in line_lower for kw in ['error:', 'fatal:', '! ', 'emergency stop']):
            return "error"
        elif any(kw in line_lower for kw in ['warning:', 'warn:', 'laTeX warning']):
            return "warning"
        elif any(kw in line_lower for kw in ['success', 'completed', 'output written']):
            return "success"
        elif any(kw in line_lower for kw in ['info:', 'note:', 'entering', 'leaving']):
            return "info"
        return "info"
    
    def clear(self) -> None:
        """Clear the log."""
        self.log_view.clear()
        self.clear_requested.emit()
    
    def _set_auto_scroll(self, enabled: bool) -> None:
        self.auto_scroll = enabled
    
    def _set_wrap(self, enabled: bool) -> None:
        self.log_view.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if enabled 
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
    
    def _filter_changed(self, filter_text: str) -> None:
        """Filter log display."""
        # This would require storing all lines and filtering
        # For now, just a placeholder
        pass
    
    def _show_context_menu(self, position) -> None:
        """Show context menu."""
        menu = QMenu(self)
        
        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(self.log_view.copy)
        
        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.log_view.selectAll)
        
        menu.addSeparator()
        
        clear_action = menu.addAction("Clear")
        clear_action.triggered.connect(self.clear)
        
        menu.exec(self.log_view.viewport().mapToGlobal(position))
    
    def set_theme(self, theme: str) -> None:
        """Change the log theme."""
        self.theme = theme
        palette = get_palette(theme)
        self._apply_level_formats(palette)
        stylesheet = qss("""
            QPlainTextEdit {
                background-color: $log_bg;
                color: $log_fg;
                border: none;
                font-family: Consolas, monospace;
            }
            QToolBar {
                background-color: $log_toolbar_bg;
                border: none;
            }
            QCheckBox {
                color: $log_checkbox_fg;
            }
            QComboBox {
                background-color: $log_combo_bg;
                color: $log_combo_fg;
                border: 1px solid $log_combo_border;
            }
        """, palette)
        if palette.name == "overleaf":
            stylesheet += web_qss("""
                QPlainTextEdit#LogView {
                    background-color: white;
                    color: $ol_text;
                    border-top: 1px solid $ol_border;
                }
                QToolBar#LogToolbar {
                    background-color: $ol_toolbar_bg;
                    border: none;
                    min-height: 30px;
                }
                QToolBar#LogToolbar QToolButton {
                    color: $ol_text;
                    border: none;
                    padding: 3px 8px;
                    font-size: 11px;
                }
                QComboBox#LogFilter {
                    background-color: white;
                    color: $ol_text;
                    border: 1px solid $ol_border;
                    border-radius: 3px;
                    padding: 2px 6px;
                }
            """)
        self.setStyleSheet(stylesheet)
    def get_text(self) -> str:
        """Get all log text."""
        return self.log_view.toPlainText()
    
    def save_to_file(self, file_path: str) -> bool:
        """Save log to file."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.get_text())
            return True
        except Exception as e:
            print(f"Failed to save log: {e}")
            return False
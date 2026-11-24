"""Main code editor widget for LaTeX editing."""

import re
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMenu, QCompleter, QTextEdit, QLineEdit,
    QCheckBox, QPushButton, QToolButton, QTabBar, QFrame, QMessageBox
)
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QTextFormat, QPainter,
    QKeyEvent, QAction, QIcon, QTextCharFormat, QSyntaxHighlighter,
    QTextDocument
)
from PyQt6.QtCore import (
    Qt, QRect, QSize, QTimer, QEvent, pyqtSignal, QStringListModel, QSignalBlocker
)

from core.themes import get_palette, qss, qcolor, web_qss

from .highlighter import LatexHighlighter, LatexCompleter


class LineNumberArea(QWidget):
    """Widget for displaying line numbers."""
    
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    
    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)
    
    def paintEvent(self, event) -> None:
        self.editor.line_number_area_paint_event(event)


class LatexEditor(QPlainTextEdit):
    """LaTeX editor with syntax highlighting, line numbers, and auto-completion."""
    
    # Signals
    cursor_position_changed = pyqtSignal(int, int)  # line, column
    file_modified = pyqtSignal(bool)
    compile_requested = pyqtSignal()
    forward_search_requested = pyqtSignal(int)  # line number
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.theme = self._get_config().get('ui.theme', 'dark')

        self._setup_editor()
        self._setup_line_numbers()
        self._setup_highlighter()
        self._setup_completer()
        self._setup_auto_save()
        
        self.current_file_path = None
        self.is_modified = False
    
    def _setup_editor(self) -> None:
        """Configure the editor."""
        config = self._get_config()
        
        # Font
        font = QFont(config.get('editor.font_family', 'Consolas'))
        font.setPointSize(config.get('editor.font_size', 11))
        font.setFixedPitch(True)
        self.setFont(font)
        
        # Tab settings
        tab_width = config.get('editor.tab_width', 4)
        use_spaces = config.get('editor.use_spaces', True)
        fm = self.fontMetrics()
        self.setTabStopDistance(fm.horizontalAdvance(' ') * tab_width)
        self.setTabChangesFocus(False)
        
        # Line wrapping
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth 
            if config.get('editor.word_wrap', False) 
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        
        # Other settings
        self.setUndoRedoEnabled(True)
        # Note: setMaximumBlockCount() disables Qt's undo stack, so leave it unset.
        
        # Connect signals
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_position_changed)
        
        # Auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)
        interval = config.get('editor.auto_save_interval', 30) * 1000
        if config.get('editor.auto_save', True):
            self.auto_save_timer.start(interval)
    
    def _get_config(self):
        """Get config instance."""
        from core.config import get_config
        return get_config()
    
    def _setup_line_numbers(self) -> None:
        """Set up line number area."""
        self.line_number_area = LineNumberArea(self)
        
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        
        self._update_line_number_area_width(0)
        self._highlight_current_line()
    
    def _setup_highlighter(self) -> None:
        """Set up syntax highlighter."""
        theme = self._get_config().get('ui.theme', 'dark')
        self.theme = theme
        self.highlighter = LatexHighlighter(self.document(), theme)
    
    def _setup_completer(self) -> None:
        """Set up auto-completion."""
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)
        
        self.completer_model = QStringListModel(self)
        self.completer.setModel(self.completer_model)
    
    def _setup_auto_save(self) -> None:
        """Set up auto-save functionality."""
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setSingleShot(False)
    
    # Line number area methods
    def line_number_area_width(self) -> int:
        """Calculate width needed for line numbers."""
        digits = len(str(max(1, self.blockCount())))
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def _update_line_number_area_width(self, _) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    
    def _update_line_number_area(self, rect, dy) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)
    
    def line_number_area_paint_event(self, event) -> None:
        palette = get_palette(self.theme)
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), qcolor(palette.line_number_bg))
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        current_block = self.textCursor().blockNumber()
        
        font = self.font()
        font.setBold(False)
        painter.setFont(font)
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                colour = (palette.line_number_active_fg if block_number == current_block
                          else palette.line_number_fg)
                painter.setPen(qcolor(colour))
                painter.drawText(
                    0, int(top), self.line_number_area.width() - 5, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
    
    def _highlight_current_line(self) -> None:
        """Highlight the current line."""
        palette = get_palette(self.theme)
        if not self._get_config().get('editor.highlight_current_line', True):
            self.setExtraSelections([])
            return
        
        extra_selections = []
        
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(qcolor(palette.current_line_bg))
            selection.format.setForeground(qcolor(palette.editor_fg))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        
        self.setExtraSelections(extra_selections)
    
    # Completion
    def _insert_completion(self, completion: str) -> None:
        """Insert the selected completion."""
        tc = self.textCursor()
        extra = len(completion) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.MoveOperation.Left)
        tc.movePosition(QTextCursor.MoveOperation.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)
    
    def _show_completer(self) -> None:
        """Show auto-completion popup."""
        prefix = self._get_word_prefix()
        if len(prefix) < 2:
            self.completer.popup().hide()
            return
        
        completions = LatexCompleter.get_completions(prefix)
        if not completions:
            self.completer.popup().hide()
            return
        
        self.completer_model.setStringList(completions)
        self.completer.setCompletionPrefix(prefix)
        
        cr = self.cursorRect()
        cr.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                    self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(cr)
    
    def _get_word_prefix(self) -> str:
        """Get the word prefix at cursor position for completion."""
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        word = tc.selectedText()
        
        # If we're after a backslash, include it
        pos = tc.position()
        if pos > 0:
            doc = self.document()
            char = doc.characterAt(pos - 1)
            if char == '\\':
                return '\\' + word
        
        return word
    
    # Event handlers
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events."""
        # Handle completer
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Escape,):
                self.completer.popup().hide()
                event.accept()
                return
        
        # Ctrl+Enter or F5 to compile
        if event.key() == Qt.Key.Key_F5 or \
           (event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.compile_requested.emit()
            event.accept()
            return
        
        # Ctrl+/ for comment toggle
        if event.key() == Qt.Key.Key_Slash and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._toggle_comment()
            event.accept()
            return

        # Ctrl+B / Ctrl+I for bold and italic
        if event.key() == Qt.Key.Key_B and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.insert_bold()
            event.accept()
            return
        if event.key() == Qt.Key.Key_I and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.insert_italic()
            event.accept()
            return
        
        # Trigger completion on backslash
        if event.text() == '\\':
            super().keyPressEvent(event)
            QTimer.singleShot(0, self._show_completer)
            return
        
        # Trigger completion on {
        if event.text() == '{':
            super().keyPressEvent(event)
            QTimer.singleShot(0, self._show_completer)
            return
        
        super().keyPressEvent(event)
    
    def _toggle_comment(self) -> None:
        """Toggle comment on selected lines."""
        cursor = self.textCursor()
        
        if cursor.hasSelection():
            # Multi-line comment toggle
            start_line = cursor.selectionStart()
            end_line = cursor.selectionEnd()
            
            cursor.beginEditBlock()
            cursor.setPosition(start_line)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            start_block = cursor.blockNumber()
            
            cursor.setPosition(end_line)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
            end_block = cursor.blockNumber()
            
            for block_num in range(start_block, end_block + 1):
                block = self.document().findBlockByNumber(block_num)
                text = block.text()
                if text.startswith('%'):
                    # Uncomment
                    cursor.setPosition(block.position())
                    cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                    cursor.deleteChar()
                else:
                    # Comment
                    cursor.setPosition(block.position())
                    cursor.insertText('%')
            cursor.endEditBlock()
        else:
            # Single line
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            text = cursor.block().text()
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            
            cursor.beginEditBlock()
            if text.startswith('%'):
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                cursor.deleteChar()
            else:
                cursor.insertText('%')
            cursor.endEditBlock()

    # Formatting helpers
    def wrap_selection(self, prefix: str, suffix: str = "") -> None:
        """Wrap the selection, or insert the pair and place the cursor inside."""
        cursor = self.textCursor()
        selected = cursor.selectedText()
        cursor.beginEditBlock()
        if selected:
            cursor.insertText(prefix + selected + suffix)
        else:
            insert_at = cursor.position()
            cursor.insertText(prefix + suffix)
            cursor.setPosition(insert_at + len(prefix))
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def apply_block_style(self, style: str) -> None:
        """Apply a sectioning or text style from the formatting ribbon."""
        commands = {
            "Normal text": ("\\textnormal{", "}"),
            "Section": ("\\section{", "}"),
            "Subsection": ("\\subsection{", "}"),
            "Subsubsection": ("\\subsubsection{", "}"),
            "Paragraph": ("\\paragraph{", "}"),
            "Subparagraph": ("\\subparagraph{", "}"),
        }
        if style in commands:
            self.wrap_selection(*commands[style])

    def insert_bold(self) -> None:
        """Wrap the selection in \\textbf{}."""
        self.wrap_selection("\\textbf{", "}")

    def insert_italic(self) -> None:
        """Wrap the selection in \\textit{}."""
        self.wrap_selection("\\textit{", "}")

    def insert_symbol(self) -> None:
        """Open the symbol picker and insert the chosen command."""
        from .symbol_picker import SymbolPickerDialog

        command = SymbolPickerDialog.pick(self)
        if not command:
            return
        if "{}" in command:
            prefix = command.split("{}", 1)[0]
            self.wrap_selection(prefix, "}")
        else:
            cursor = self.textCursor()
            cursor.insertText(command)
            self.setTextCursor(cursor)

    def _on_text_changed(self) -> None:
        """Handle text changes."""
        was_modified = self.is_modified
        self.is_modified = self.document().isModified()
        
        if was_modified != self.is_modified:
            self.file_modified.emit(self.is_modified)
    
    def _on_cursor_position_changed(self) -> None:
        """Handle cursor position changes."""
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.positionInBlock() + 1
        self.cursor_position_changed.emit(line, column)
    
    def _auto_save(self) -> None:
        """Auto-save the current file."""
        if self.is_modified and self.current_file_path:
            self._save_to_file(self.current_file_path)
    
    # Public methods
    def load_file(self, file_path: str) -> bool:
        """Load a file into the editor."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.setPlainText(content)
            self.current_file_path = file_path
            self.document().setModified(False)
            self.is_modified = False
            self.file_modified.emit(False)
            return True
        except Exception as e:
            print(f"Failed to load file: {e}")
            return False
    
    def save_file(self, file_path: str = None) -> bool:
        """Save the current file."""
        path = file_path or self.current_file_path
        if not path:
            return False
        return self._save_to_file(path)
    
    def _save_to_file(self, file_path: str) -> bool:
        """Save content to file."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.toPlainText())
            
            self.current_file_path = file_path
            self.document().setModified(False)
            self.is_modified = False
            self.file_modified.emit(False)
            return True
        except Exception as e:
            print(f"Failed to save file: {e}")
            return False
    
    def get_current_line(self) -> int:
        """Get current line number (1-based)."""
        return self.textCursor().blockNumber() + 1

    def get_current_column(self) -> int:
        """Get current column number (1-based)."""
        return self.textCursor().positionInBlock() + 1

    def get_current_file_path(self) -> Optional[str]:
        """Get the path of the file currently open in the editor."""
        return self.current_file_path
    
    def goto_line(self, line: int, column: int = 1) -> None:
        """Go to a specific line and column (both 1-based)."""
        block = self.document().findBlockByNumber(line - 1)
        if block.isValid():
            offset = max(0, min(column - 1, max(0, block.length() - 1)))
            cursor = self.textCursor()
            cursor.setPosition(block.position() + offset)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
    
    def set_theme(self, theme: str) -> None:
        """Change the editor theme."""
        self.theme = theme
        palette = get_palette(theme)
        self.highlighter.set_theme(theme)

        self.setStyleSheet(qss("""
            QPlainTextEdit {
                background-color: $editor_bg;
                color: $editor_fg;
                selection-background-color: $editor_selection;
                border: 1px solid $editor_border;
                caret-color: $caret;
            }
        """, palette))
        self.line_number_area.setStyleSheet(
            qss("QWidget { background-color: $line_number_bg; }", palette)
        )
        self._highlight_current_line()
        self.line_number_area.update()
    
    def find_text(self, text: str, case_sensitive: bool = False, 
                  whole_words: bool = False, backward: bool = False) -> bool:
        """Find text in the document."""
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_words:
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        
        return self.find(text, flags)
    
    def replace_text(self, find_text: str, replace_text: str, 
                     case_sensitive: bool = False, whole_words: bool = False) -> int:
        """Replace all occurrences in the document."""
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_words:
            flags |= QTextDocument.FindFlag.FindWholeWords

        count = 0
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)

        while self.find(find_text, flags):
            cursor = self.textCursor()
            if cursor.hasSelection():
                cursor.insertText(replace_text)
                count += 1
        
        cursor.endEditBlock()
        return count
    
    def contextMenuEvent(self, event) -> None:
        """Show context menu."""
        menu = self.createStandardContextMenu()
        
        # Add custom actions
        menu.addSeparator()
        
        compile_action = menu.addAction("Compile (F5)")
        compile_action.triggered.connect(self.compile_requested.emit)
        
        forward_search_action = menu.addAction("Forward Search")
        forward_search_action.triggered.connect(
            lambda: self.forward_search_requested.emit(self.get_current_line())
        )
        
        menu.addSeparator()
        
        comment_action = menu.addAction("Toggle Comment (Ctrl+/)")
        comment_action.triggered.connect(self._toggle_comment)
        
        menu.exec(event.globalPos())


class EditorWidget(QWidget):
    """Container widget for the editor with toolbar."""
    
    compile_requested = pyqtSignal()
    file_modified = pyqtSignal(bool)
    cursor_position_changed = pyqtSignal(int, int)
    forward_search_requested = pyqtSignal(int)
    outline_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        from PyQt6.QtWidgets import QToolBar, QComboBox, QSpinBox
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))
        
        # File operations
        self.new_file_btn = self.toolbar.addAction("New")
        self.open_file_btn = self.toolbar.addAction("Open")
        self.save_file_btn = self.toolbar.addAction("Save")
        self.toolbar.addSeparator()
        
        # Edit operations
        self.undo_btn = self.toolbar.addAction("Undo")
        self.redo_btn = self.toolbar.addAction("Redo")
        self.toolbar.addSeparator()
        
        # Find/Replace
        self.find_btn = self.toolbar.addAction("Find")
        self.replace_btn = self.toolbar.addAction("Replace")
        self.toolbar.addSeparator()

        # Edit mode toggle
        self.edit_mode_action = self.toolbar.addAction("Edit Mode")
        self.edit_mode_action.setCheckable(True)
        self.edit_mode_action.setToolTip("Show the LaTeX formatting ribbon")
        self.toolbar.addSeparator()
        
        # Compile
        self.compile_btn = self.toolbar.addAction("Compile")
        self.compile_btn.setToolTip("Compile (F5)")
        self.toolbar.addSeparator()
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(11)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self.toolbar.addWidget(self.font_size_spin)

        # Source / Visual segmented control from the reference toolbar.
        self.mode_widget = QWidget()
        mode_layout = QHBoxLayout(self.mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(0)
        self.source_mode_btn = QToolButton()
        self.source_mode_btn.setText("Code Editor")
        self.source_mode_btn.setCheckable(True)
        self.source_mode_btn.setChecked(True)
        self.source_mode_btn.setObjectName("SourceModeButton")
        self.visual_mode_btn = QToolButton()
        self.visual_mode_btn.setText("Visual")
        self.visual_mode_btn.setCheckable(True)
        self.visual_mode_btn.setObjectName("VisualModeButton")
        mode_layout.addWidget(self.source_mode_btn)
        mode_layout.addWidget(self.visual_mode_btn)
        self.toolbar.addWidget(self.mode_widget)

        layout.addWidget(self.toolbar)

        # Open-file tab strip matching the web editor's file tabs.
        self._documents = []
        self._updating_tabs = False
        self._applying_document = False
        self._active_index = 0
        self.file_tab_bar = QTabBar()
        self.file_tab_bar.setObjectName("EditorTabs")
        self.file_tab_bar.setShape(QTabBar.Shape.RoundedSouth)
        self.file_tab_bar.setDrawBase(False)
        self.file_tab_bar.setFixedHeight(30)
        self.file_tab_bar.setTabsClosable(True)
        self._documents.append(self._blank_document())
        self._updating_tabs = True
        self.file_tab_bar.addTab("Untitled")
        self._updating_tabs = False
        self.file_tab_bar.tabCloseRequested.connect(self._close_tab)
        self.file_tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.file_tab_bar)

        self._outline_timer = QTimer(self)
        self._outline_timer.setSingleShot(True)
        self._outline_timer.timeout.connect(self._emit_outline)

        # Formatting ribbon (shown only in Edit Mode)
        self.format_ribbon = QWidget()
        ribbon_layout = QHBoxLayout(self.format_ribbon)
        ribbon_layout.setContentsMargins(4, 2, 4, 2)
        ribbon_layout.setSpacing(4)

        ribbon_layout.addWidget(QLabel("Style:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "Normal text", "Section", "Subsection", "Subsubsection",
            "Paragraph", "Subparagraph",
        ])
        ribbon_layout.addWidget(self.style_combo)
        ribbon_layout.addSpacing(8)

        self.ribbon_bold_btn = QToolButton()
        self.ribbon_bold_btn.setText("B")
        bold_font = self.ribbon_bold_btn.font()
        bold_font.setBold(True)
        self.ribbon_bold_btn.setFont(bold_font)
        self.ribbon_bold_btn.setToolTip("Bold (Ctrl+B)")
        ribbon_layout.addWidget(self.ribbon_bold_btn)

        self.ribbon_italic_btn = QToolButton()
        self.ribbon_italic_btn.setText("I")
        italic_font = self.ribbon_italic_btn.font()
        italic_font.setItalic(True)
        self.ribbon_italic_btn.setFont(italic_font)
        self.ribbon_italic_btn.setToolTip("Italic (Ctrl+I)")
        ribbon_layout.addWidget(self.ribbon_italic_btn)

        self.ribbon_symbol_btn = QToolButton()
        self.ribbon_symbol_btn.setText("Ω")
        self.ribbon_symbol_btn.setToolTip("Insert symbol")
        ribbon_layout.addWidget(self.ribbon_symbol_btn)
        ribbon_layout.addSpacing(8)

        self.ribbon_undo_btn = QToolButton()
        self.ribbon_undo_btn.setText("Undo")
        ribbon_layout.addWidget(self.ribbon_undo_btn)

        self.ribbon_redo_btn = QToolButton()
        self.ribbon_redo_btn.setText("Redo")
        ribbon_layout.addWidget(self.ribbon_redo_btn)
        ribbon_layout.addStretch()

        layout.addWidget(self.format_ribbon)

        # Find / replace bar
        self.find_bar = QWidget()
        find_layout = QHBoxLayout(self.find_bar)
        find_layout.setContentsMargins(4, 2, 4, 2)
        find_layout.setSpacing(4)

        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find...")
        self.find_edit.returnPressed.connect(self.find_next)
        find_layout.addWidget(self.find_edit)

        self.find_prev_btn = QToolButton()
        self.find_prev_btn.setText("◀")
        self.find_prev_btn.setToolTip("Find previous")
        self.find_prev_btn.clicked.connect(self.find_previous)
        find_layout.addWidget(self.find_prev_btn)

        self.find_next_btn = QToolButton()
        self.find_next_btn.setText("▶")
        self.find_next_btn.setToolTip("Find next")
        self.find_next_btn.clicked.connect(self.find_next)
        find_layout.addWidget(self.find_next_btn)

        self.case_check = QCheckBox("Aa")
        self.case_check.setToolTip("Case sensitive")
        find_layout.addWidget(self.case_check)

        self.whole_check = QCheckBox("Whole")
        self.whole_check.setToolTip("Whole words only")
        find_layout.addWidget(self.whole_check)

        find_layout.addSpacing(8)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Replace with...")
        find_layout.addWidget(self.replace_edit)

        self.replace_one_btn = QPushButton("Replace")
        self.replace_one_btn.clicked.connect(self.replace_current)
        find_layout.addWidget(self.replace_one_btn)

        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.clicked.connect(self.replace_all)
        find_layout.addWidget(self.replace_all_btn)

        self.close_find_btn = QToolButton()
        self.close_find_btn.setText("×")
        self.close_find_btn.setToolTip("Close")
        self.close_find_btn.clicked.connect(self.hide_find)
        find_layout.addWidget(self.close_find_btn)
        self.find_bar.setVisible(False)

        self.visual_banner = QLabel(
            "Visual mode is a preview of the Overleaf web layout. "
            "Use Code Editor to edit LaTeX source."
        )
        self.visual_banner.setObjectName("VisualBanner")
        self.visual_banner.setWordWrap(True)
        self.visual_banner.setVisible(False)
        layout.addWidget(self.visual_banner)

        # Editor
        self.editor = LatexEditor()
        self.editor.compile_requested.connect(self.compile_requested.emit)
        self.editor.file_modified.connect(self._on_editor_file_modified)
        self.editor.cursor_position_changed.connect(self.cursor_position_changed.emit)
        self.editor.forward_search_requested.connect(self.forward_search_requested.emit)
        self.editor.textChanged.connect(self._schedule_outline)
        
        layout.addWidget(self.editor)
        self._apply_document(0)
        
        # Connect toolbar actions
        self.new_file_btn.triggered.connect(self.new_file)
        self.open_file_btn.triggered.connect(self.open_file)
        self.save_file_btn.triggered.connect(self.save_file)
        self.undo_btn.triggered.connect(self.undo)
        self.redo_btn.triggered.connect(self.redo)
        self.find_btn.triggered.connect(lambda: self.show_find(False))
        self.replace_btn.triggered.connect(lambda: self.show_find(True))
        self.compile_btn.triggered.connect(self.compile_requested.emit)
        self.edit_mode_action.toggled.connect(self._set_edit_mode)
        self.source_mode_btn.clicked.connect(lambda: self._set_visual_mode(False))
        self.visual_mode_btn.clicked.connect(lambda: self._set_visual_mode(True))
        self.editor.undoAvailable.connect(self.undo_btn.setEnabled)
        self.editor.redoAvailable.connect(self.redo_btn.setEnabled)

        # Connect ribbon actions
        self.style_combo.textActivated.connect(self._apply_style)
        self.ribbon_bold_btn.clicked.connect(self._format_bold)
        self.ribbon_italic_btn.clicked.connect(self._format_italic)
        self.ribbon_symbol_btn.clicked.connect(self._insert_symbol)
        self.ribbon_undo_btn.clicked.connect(self.undo)
        self.ribbon_redo_btn.clicked.connect(self.redo)

        # Restore persisted Edit Mode state
        edit_mode = self._get_config().get('editor.edit_mode', False)
        self.edit_mode_action.setChecked(edit_mode)
        self.format_ribbon.setVisible(edit_mode)
    
    def _get_config(self):
        """Get config instance."""
        from core.config import get_config
        return get_config()

    def _set_edit_mode(self, checked: bool) -> None:
        """Show or hide the formatting ribbon and persist the choice."""
        self.format_ribbon.setVisible(checked)
        self._get_config().set('editor.edit_mode', checked)

    def _set_visual_mode(self, visual: bool) -> None:
        """Toggle the web-style Visual mode banner without hiding the source."""
        self.source_mode_btn.setChecked(not visual)
        self.visual_mode_btn.setChecked(visual)
        self.visual_banner.setVisible(visual)
    
    def _on_font_size_changed(self, size: int) -> None:
        font = self.editor.font()
        font.setPointSize(size)
        self.editor.setFont(font)
    
    # Multi-document helpers
    @staticmethod
    def _blank_document() -> dict:
        return {"path": None, "text": "", "cursor": 0, "modified": False}

    def _current_index(self) -> int:
        return self.file_tab_bar.currentIndex()

    def _capture_current_doc(self) -> None:
        """Store the live editor state into the active document entry."""
        index = self._active_index
        if index < 0 or index >= len(self._documents) or self._applying_document:
            return
        doc = self._documents[index]
        cursor = self.editor.textCursor()
        doc["text"] = self.editor.toPlainText()
        doc["cursor"] = cursor.position()
        doc["modified"] = self.editor.document().isModified()
        doc["path"] = self.editor.current_file_path
        self._update_tab_title(index)

    def _update_tab_title(self, index: int) -> None:
        if index < 0 or index >= len(self._documents):
            return
        doc = self._documents[index]
        name = Path(doc["path"]).name if doc["path"] else "Untitled"
        if doc["modified"]:
            name += "*"
        self.file_tab_bar.setTabText(index, name)

    def _apply_document(self, index: int) -> None:
        """Load a stored document into the single live editor widget."""
        if index < 0 or index >= len(self._documents):
            return
        doc = self._documents[index]
        self._active_index = index
        self._applying_document = True
        with QSignalBlocker(self.editor):
            self.editor.setPlainText(doc["text"])
            self.editor.current_file_path = doc["path"]
            self.editor.document().setModified(doc["modified"])
            self.editor.is_modified = doc["modified"]
            cursor = self.editor.textCursor()
            cursor.setPosition(max(0, min(doc["cursor"], len(doc["text"]))))
            self.editor.setTextCursor(cursor)
        self._applying_document = False
        self._update_tab_title(index)
        self.file_modified.emit(doc["modified"])
        cursor = self.editor.textCursor()
        self.cursor_position_changed.emit(
            cursor.blockNumber() + 1, cursor.positionInBlock() + 1
        )
        self._emit_outline()

    def _set_current_index(self, index: int) -> None:
        """Programmatically select a tab without reacting to the signal twice."""
        self._updating_tabs = True
        self.file_tab_bar.setCurrentIndex(index)
        self._updating_tabs = False
        self._apply_document(index)

    def _on_tab_changed(self, index: int) -> None:
        if self._updating_tabs:
            return
        self._capture_current_doc()
        self._apply_document(index)

    def _close_tab(self, index: int) -> None:
        """Close one tab, prompting to save unsaved work."""
        if index < 0 or index >= len(self._documents):
            return

        if self._documents[index]["modified"]:
            self._set_current_index(index)
            name = Path(self._documents[index]["path"]).name \
                if self._documents[index]["path"] else "Untitled"
            answer = QMessageBox.question(
                self,
                "Unsaved Changes",
                f'Save changes to "{name}" before closing?',
                buttons=QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                defaultButton=QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self.save_file()
                if self._documents[index]["modified"]:
                    return

        self._updating_tabs = True
        self.file_tab_bar.removeTab(index)
        self._documents.pop(index)
        self._updating_tabs = False

        if not self._documents:
            self._documents.append(self._blank_document())
            self.file_tab_bar.addTab("Untitled")
            index = 0
        else:
            index = min(index, len(self._documents) - 1)
        self._set_current_index(index)

    def close_current_file(self) -> None:
        """Close the active editor tab."""
        self._close_tab(self._current_index())

    def load_file(self, file_path: str) -> bool:
        """Open a file in its own tab, or switch to it if already open."""
        path = Path(file_path).resolve()
        for index, doc in enumerate(self._documents):
            if doc["path"] and Path(doc["path"]).resolve() == path:
                self._set_current_index(index)
                return True

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Failed to load file: {e}")
            return False

        self._capture_current_doc()
        index = self._current_index()
        doc = self._documents[index]
        if (len(self._documents) == 1 and doc["path"] is None
                and not doc["modified"] and not doc["text"]):
            doc.update(path=str(path), text=content, cursor=0, modified=False)
            self._set_current_index(index)
        else:
            self._documents.append({
                "path": str(path), "text": content,
                "cursor": 0, "modified": False,
            })
            self.file_tab_bar.addTab(path.name)
            self._set_current_index(len(self._documents) - 1)
        return True

    def save_file(self, file_path: str = None) -> bool:
        return self.editor.save_file(file_path)

    def new_file(self) -> None:
        self._capture_current_doc()
        self._documents.append(self._blank_document())
        self.file_tab_bar.addTab("Untitled")
        self._set_current_index(len(self._documents) - 1)

    def _on_editor_file_modified(self, modified: bool) -> None:
        if self._applying_document:
            return
        index = self._active_index
        if 0 <= index < len(self._documents):
            doc = self._documents[index]
            cursor = self.editor.textCursor()
            doc.update(
                path=self.editor.current_file_path,
                text=self.editor.toPlainText(),
                cursor=cursor.position(),
                modified=modified,
            )
            self._update_tab_title(index)
        self.file_modified.emit(modified)

    def _schedule_outline(self) -> None:
        if not self._applying_document:
            self._outline_timer.start(120)

    def _emit_outline(self) -> None:
        if self._applying_document:
            return
        self.outline_changed.emit(self._parse_outline(self.editor.toPlainText()))

    @staticmethod
    def _parse_outline(text: str) -> list:
        pattern = re.compile(
            r"\\(chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\s*\{([^{}]*)\}"
        )
        items = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                title = match.group(2).strip() or match.group(1).capitalize()
                items.append((title, line_number))
        return items

    def open_file(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open LaTeX File", "", "LaTeX Files (*.tex);;All Files (*)"
        )
        if file_path:
            self.load_file(file_path)
    
    def get_current_line(self) -> int:
        return self.editor.get_current_line()

    def get_current_column(self) -> int:
        return self.editor.get_current_column()

    def get_current_file_path(self) -> Optional[str]:
        return self.editor.get_current_file_path()
    
    def goto_line(self, line: int, column: int = 1) -> None:
        self.editor.goto_line(line, column)

    # Editor action helpers
    def undo(self) -> None:
        self.editor.undo()
        self.editor.setFocus()

    def redo(self) -> None:
        self.editor.redo()
        self.editor.setFocus()

    def _apply_style(self, style: str) -> None:
        self.editor.apply_block_style(style)
        self.editor.setFocus()

    def _format_bold(self) -> None:
        self.editor.insert_bold()
        self.editor.setFocus()

    def _format_italic(self) -> None:
        self.editor.insert_italic()
        self.editor.setFocus()

    def _insert_symbol(self) -> None:
        self.editor.insert_symbol()
        self.editor.setFocus()

    # Find / replace bar
    def _find_flags(self) -> tuple:
        return self.case_check.isChecked(), self.whole_check.isChecked()

    def _show_replace_controls(self, visible: bool) -> None:
        self.replace_edit.setVisible(visible)
        self.replace_one_btn.setVisible(visible)
        self.replace_all_btn.setVisible(visible)

    def find_next(self, backward: bool = False) -> bool:
        text = self.find_edit.text()
        if not text:
            return False
        case_sensitive, whole_words = self._find_flags()
        found = self.editor.find_text(text, case_sensitive, whole_words, backward)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward
                else QTextCursor.MoveOperation.Start
            )
            self.editor.setTextCursor(cursor)
            found = self.editor.find_text(text, case_sensitive, whole_words, backward)
        self.editor.setFocus()
        return found

    def find_previous(self) -> bool:
        return self.find_next(backward=True)

    def replace_current(self) -> None:
        text = self.find_edit.text()
        if not text:
            return
        case_sensitive, whole_words = self._find_flags()
        cursor = self.editor.textCursor()
        selected = cursor.selectedText()
        matches = (
            selected == text if case_sensitive
            else selected.lower() == text.lower()
        )
        if not matches:
            self.find_next()
            cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_edit.text())
            self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def replace_all(self) -> None:
        text = self.find_edit.text()
        if not text:
            return
        case_sensitive, whole_words = self._find_flags()
        count = self.editor.replace_text(
            text, self.replace_edit.text(), case_sensitive, whole_words
        )
        self.replace_all_btn.setToolTip(f"Replaced {count} occurrence(s)")
        self.editor.setFocus()

    def hide_find(self) -> None:
        self.find_bar.setVisible(False)
        self.editor.setFocus()

    def show_find(self, replace: bool = False) -> None:
        self.find_bar.setVisible(True)
        self._show_replace_controls(replace)
        (self.replace_edit if replace else self.find_edit).setFocus()
        (self.replace_edit if replace else self.find_edit).selectAll()
    
    def set_theme(self, theme: str) -> None:
        self.editor.set_theme(theme)
        palette = get_palette(theme)
        bar_stylesheet = qss("""
            QWidget { background-color: $toolbar_bg; }
            QLabel, QCheckBox { color: $foreground; }
            QComboBox, QLineEdit {
                background-color: $input_bg;
                color: $input_fg;
                border: 1px solid $input_border;
                padding: 2px 6px;
            }
            QToolButton, QPushButton {
                color: $foreground;
                border: 1px solid transparent;
                padding: 3px 6px;
                border-radius: 3px;
            }
            QToolButton:hover, QPushButton:hover {
                background-color: $toolbar_button_hover;
            }
            QToolButton:pressed, QPushButton:pressed {
                background-color: $toolbar_button_pressed;
            }
        """, palette)
        if palette.name == "overleaf":
            bar_stylesheet += web_qss("""
                QToolBar {
                    background-color: $ol_toolbar_bg;
                    border-bottom: 1px solid $ol_border;
                    min-height: 34px;
                }
                QToolButton#SourceModeButton,
                QToolButton#VisualModeButton {
                    background-color: white;
                    color: $ol_muted;
                    border: 1px solid $ol_border;
                    padding: 3px 10px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QToolButton#SourceModeButton {
                    border-top-right-radius: 0px;
                    border-bottom-right-radius: 0px;
                }
                QToolButton#VisualModeButton {
                    border-left: none;
                    border-top-left-radius: 0px;
                    border-bottom-left-radius: 0px;
                }
                QToolButton#SourceModeButton:checked,
                QToolButton#VisualModeButton:checked {
                    background-color: $ol_green;
                    color: white;
                    border-color: $ol_green;
                }
            """)
        self.toolbar.setStyleSheet(bar_stylesheet)
        self.file_tab_bar.setStyleSheet(qss("""
            QTabBar::tab {
                background-color: $toolbar_bg;
                color: $foreground;
                border: 1px solid $editor_border;
                padding: 5px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: $editor_bg;
                color: $editor_fg;
                border-bottom: 2px solid $progress_bg;
            }
        """, palette))
        self.visual_banner.setStyleSheet(web_qss("""
            QLabel#VisualBanner {
                background-color: #fff7e6;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 4px;
                padding: 6px 10px;
                margin: 4px 6px;
                font-size: 11px;
            }
        """))
        self.format_ribbon.setStyleSheet(bar_stylesheet)
        self.find_bar.setStyleSheet(bar_stylesheet)
    
    def find_text(self, text: str, case_sensitive: bool = False,
                  whole_words: bool = False, backward: bool = False) -> bool:
        return self.editor.find_text(text, case_sensitive, whole_words, backward)
    
    def replace_text(self, find_text: str, replace_text: str,
                     case_sensitive: bool = False, whole_words: bool = False) -> int:
        return self.editor.replace_text(find_text, replace_text, case_sensitive, whole_words)
    
    def show_replace(self) -> None:
        """Open the bar with replace controls visible."""
        self.show_find(True)
    
    def get_text(self) -> str:
        return self.editor.toPlainText()
    
    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
        self._capture_current_doc()
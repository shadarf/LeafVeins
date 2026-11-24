"""File tree widget for project navigation."""

import os
import fnmatch
from pathlib import Path
from PyQt6.QtWidgets import (
    QTreeView, QWidget, QVBoxLayout,
    QMenu, QLineEdit, QToolBar, QMessageBox, QInputDialog,
    QListWidget, QListWidgetItem, QPushButton
)
from PyQt6.QtGui import QIcon, QFont, QCursor, QFileSystemModel, QAction
from PyQt6.QtCore import Qt, QModelIndex, pyqtSignal, QDir, QSortFilterProxyModel, QRegularExpression

from core.themes import get_palette, qss, web_qss


class FileTreeFilterModel(QSortFilterProxyModel):
    """Filter model to hide unwanted files using regex."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # Regex to exclude unwanted file patterns (negative lookahead)
        # Matches any filename that does NOT end with the excluded extensions
        self.hidden_extensions = [
            'aux', 'log', 'out', 'toc', 'lof', 'lot',
            'bbl', 'blg', 'synctex.gz', 'fls', 'fdb_latexmk',
            'pdf', 'dvi', 'ps', 'nav', 'snm', 'vrb',
            'bcf', 'run.xml', 'xml', 'ist', 'glg', 'glo',
            'gls', 'acn', 'acr', 'alg', 'xdy', 'tdo',
            'pyc', 'pyo', 'swp', 'swo', 'DS_Store', 'Thumbs.db',
        ]
        # Build regex pattern
        ext_pattern = '|'.join(fnmatch.translate(ext).replace(r'\Z', '') for ext in self.hidden_extensions)
        # Negative lookahead: match if NOT ending with any of these
        # Anchor the extension to end of string ($) to only hide files whose FINAL extension matches
        regex_pattern = f'^(?!.*\\.(?:{ext_pattern})$).*$'
        self.setFilterRegularExpression(QRegularExpression(regex_pattern))
    
    # Don't override filterAcceptsRow or lessThan - they cause crashes
    # when calling isDir() on the source model during filtering/sorting
    # The regex filter handles file extension filtering
    # Hidden directories (starting with .) will still show but that's acceptable


class FileTreeWidget(QWidget):
    """Project file tree with context menu and file operations."""
    
    file_opened = pyqtSignal(str)  # file path
    file_created = pyqtSignal(str)  # file path
    file_deleted = pyqtSignal(str)  # file path
    file_renamed = pyqtSignal(str, str)  # old path, new path
    compile_requested = pyqtSignal()
    project_changed = pyqtSignal(str)  # project path
    outline_item_clicked = pyqtSignal(int)  # 1-based source line
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_root = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(self.toolbar.iconSize())
        
        self.new_file_action = self.toolbar.addAction("New File")
        self.new_folder_action = self.toolbar.addAction("New Folder")
        self.toolbar.addSeparator()
        self.refresh_action = self.toolbar.addAction("Refresh")
        self.collapse_action = self.toolbar.addAction("Collapse All")
        self.toolbar.addSeparator()
        self.compile_action = self.toolbar.addAction("Compile")
        
        layout.addWidget(self.toolbar)
        
        # Search/filter
        self.filter_edit = QLineEdit()
        self.filter_edit.setObjectName("TreeFilter")
        self.filter_edit.setPlaceholderText("Filter files...")
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.filter_edit)
        
        # Tree view
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(15)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        
        # File system model - created but not connected yet
        self.model = QFileSystemModel()
        self.model.setReadOnly(False)
        
        # Filter model
        self.filter_model = FileTreeFilterModel()
        
        # Don't connect model to filter_model yet - will do in set_project_root
        # to avoid crash when calling setRootPath on connected model
        
        layout.addWidget(self.tree)

        # File outline section from the reference sidebar.
        self.outline_toggle = QPushButton("▾  File Outline  (0)")
        self.outline_toggle.setObjectName("OutlineToggle")
        self.outline_toggle.setCheckable(True)
        self.outline_toggle.setChecked(True)
        layout.addWidget(self.outline_toggle)

        self.outline_list = QListWidget()
        self.outline_list.setObjectName("OutlineList")
        self.outline_list.setMaximumHeight(140)
        self.outline_list.addItem("No section headings detected")
        self.outline_list.itemClicked.connect(self._on_outline_item_clicked)
        self.outline_toggle.toggled.connect(self.outline_list.setVisible)
        layout.addWidget(self.outline_list)
        
        # Connect toolbar actions
        self.new_file_action.triggered.connect(self._new_file)
        self.new_folder_action.triggered.connect(self._new_folder)
        self.refresh_action.triggered.connect(self.refresh)
        self.collapse_action.triggered.connect(self.tree.collapseAll)
        self.compile_action.triggered.connect(self.compile_requested.emit)
        
        # Connect model signals
        self.model.directoryLoaded.connect(self._on_directory_loaded)
    
    def set_project_root(self, path: str) -> None:
        """Set the project root directory."""
        self.project_root = Path(path).resolve()
        path_str = str(self.project_root)
        
        # Set model root FIRST (before connecting filter_model) to avoid crash
        root_index = self.model.setRootPath(path_str)
        
        # Connect filter model to source model
        self.filter_model.setSourceModel(self.model)
        
        # Wait for directory to load before setting model on tree view
        # This avoids crash in filterAcceptsRow during initial filtering
        from PyQt6.QtWidgets import QApplication
        import time
        
        loaded = [False]
        def on_loaded(loaded_path):
            if os.path.normpath(loaded_path) == os.path.normpath(path_str):
                loaded[0] = True
        
        self.model.directoryLoaded.connect(on_loaded)
        
        # Process events to allow directory loading
        for _ in range(100):
            QApplication.processEvents()
            time.sleep(0.02)
            if loaded[0]:
                break
        
        # Now set model on tree view (safe to do after directory loaded)
        self.tree.setModel(self.filter_model)
        
        # Hide columns except name
        for col in range(1, self.model.columnCount()):
            self.tree.hideColumn(col)
        
        # Map to proxy and set on tree
        proxy_index = self.filter_model.mapFromSource(root_index)
        self.tree.setRootIndex(proxy_index)
        
        # Expand root
        self.tree.expand(proxy_index)
        
        # Set up file watcher for auto-refresh
        self._setup_file_watcher()
        
        self.project_changed.emit(path_str)
    
    def _setup_file_watcher(self) -> None:
        """Set up file system watcher for auto-refresh."""
        from PyQt6.QtCore import QFileSystemWatcher
        if hasattr(self, '_watcher'):
            self._watcher.deleteLater()
        
        self._watcher = QFileSystemWatcher([str(self.project_root)], self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
    
    def _on_directory_changed(self, path: str) -> None:
        """Handle directory changes."""
        if not self.project_root:
            return
        
        path_str = str(self.project_root)
        
        # Disconnect tree model to avoid crash during refresh
        self.tree.setModel(None)
        
        # Force refresh
        self.model.setRootPath("")
        root_index = self.model.setRootPath(path_str)
        
        # Wait for directory to load
        from PyQt6.QtWidgets import QApplication
        import time
        
        loaded = [False]
        def on_loaded(loaded_path):
            if os.path.normpath(loaded_path) == os.path.normpath(path_str):
                loaded[0] = True
        
        self.model.directoryLoaded.connect(on_loaded)
        
        for _ in range(100):
            QApplication.processEvents()
            time.sleep(0.02)
            if loaded[0]:
                break
        
        # Reconnect tree model
        self.tree.setModel(self.filter_model)
        
        # Hide columns
        for col in range(1, self.model.columnCount()):
            self.tree.hideColumn(col)
        
        # Reset root index
        proxy_index = self.filter_model.mapFromSource(root_index)
        self.tree.setRootIndex(proxy_index)
        self.tree.expand(proxy_index)
    
    def _on_directory_loaded(self, path: str) -> None:
        """Handle directory loaded."""
        pass
    
    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text changes."""
        self.filter_model.setFilterFixedString(text)
        if text:
            self.tree.expandAll()
    
    def _on_double_click(self, index: QModelIndex) -> None:
        """Handle double-click on tree item."""
        source_index = self.filter_model.mapToSource(index)
        if source_index.isValid() and not self.model.isDir(source_index):
            file_path = self.model.filePath(source_index)
            self.file_opened.emit(file_path)
    
    def _show_context_menu(self, position) -> None:
        """Show context menu for tree items."""
        index = self.tree.indexAt(position)
        
        menu = QMenu(self)
        
        if index.isValid():
            source_index = self.filter_model.mapToSource(index)
            file_path = self.model.filePath(source_index)
            is_dir = self.model.isDir(source_index)
            
            if is_dir:
                new_file_action = menu.addAction("New File Here")
                new_file_action.triggered.connect(lambda: self._new_file_in_dir(file_path))
                
                new_folder_action = menu.addAction("New Folder Here")
                new_folder_action.triggered.connect(lambda: self._new_folder_in_dir(file_path))
                
                menu.addSeparator()
                
                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self._rename(file_path))
                
                delete_action = menu.addAction("Delete")
                delete_action.triggered.connect(lambda: self._delete(file_path))
            else:
                open_action = menu.addAction("Open")
                open_action.triggered.connect(lambda: self.file_opened.emit(file_path))
                
                set_main_action = menu.addAction("Set as Main File")
                set_main_action.triggered.connect(lambda: self._set_main_file(file_path))
                
                menu.addSeparator()
                
                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self._rename(file_path))
                
                delete_action = menu.addAction("Delete")
                delete_action.triggered.connect(lambda: self._delete(file_path))
        else:
            # Clicked on empty space - root level actions
            new_file_action = menu.addAction("New File")
            new_file_action.triggered.connect(self._new_file)
            
            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(self._new_folder)
        
        menu.exec(self.tree.viewport().mapToGlobal(position))
    
    def _new_file(self) -> None:
        """Create a new file in the project root."""
        self._new_file_in_dir(str(self.project_root))
    
    def _new_file_in_dir(self, dir_path: str) -> None:
        """Create a new file in the specified directory."""
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            file_path = Path(dir_path) / name
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.touch()
                self.file_created.emit(str(file_path))
                self.file_opened.emit(str(file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create file: {e}")
    
    def _new_folder(self) -> None:
        """Create a new folder in the project root."""
        self._new_folder_in_dir(str(self.project_root))
    
    def _new_folder_in_dir(self, dir_path: str) -> None:
        """Create a new folder in the specified directory."""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            folder_path = Path(dir_path) / name
            try:
                folder_path.mkdir(parents=True, exist_ok=True)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create folder: {e}")
    
    def _rename(self, old_path: str) -> None:
        """Rename a file or folder."""
        old = Path(old_path)
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old.name)
        if ok and name and name != old.name:
            new_path = old.parent / name
            try:
                old.rename(new_path)
                self.file_renamed.emit(str(old), str(new_path))
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename: {e}")
    
    def _delete(self, path: str) -> None:
        """Delete a file or folder."""
        p = Path(path)
        msg = f"Delete '{p.name}'?"
        if p.is_dir():
            msg += " (and all contents)"
        
        reply = QMessageBox.question(
            self, "Confirm Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if p.is_file():
                    p.unlink()
                else:
                    import shutil
                    shutil.rmtree(p)
                self.file_deleted.emit(str(p))
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
    
    def _set_main_file(self, file_path: str) -> None:
        """Set a file as the main LaTeX file."""
        # This would be handled by the project manager
        # Emit signal or call project manager directly
        from core.database import get_database
        db = get_database()
        # We'd need project_id - for now just emit signal
        self.file_opened.emit(file_path)  # Reuse for now
    
    def refresh(self) -> None:
        """Refresh the file tree."""
        if not self.project_root:
            return
        
        path_str = str(self.project_root)
        
        # Disconnect tree model to avoid crash during refresh
        self.tree.setModel(None)
        
        # Force refresh
        self.model.setRootPath("")
        root_index = self.model.setRootPath(path_str)
        
        # Wait for directory to load
        from PyQt6.QtWidgets import QApplication
        import time
        
        loaded = [False]
        def on_loaded(loaded_path):
            if os.path.normpath(loaded_path) == os.path.normpath(path_str):
                loaded[0] = True
        
        self.model.directoryLoaded.connect(on_loaded)
        
        for _ in range(100):
            QApplication.processEvents()
            time.sleep(0.02)
            if loaded[0]:
                break
        
        # Reconnect tree model
        self.tree.setModel(self.filter_model)
        
        # Hide columns
        for col in range(1, self.model.columnCount()):
            self.tree.hideColumn(col)
        
        # Reset root index
        proxy_index = self.filter_model.mapFromSource(root_index)
        self.tree.setRootIndex(proxy_index)
        self.tree.expand(proxy_index)
    
    def expand_all(self) -> None:
        """Expand all tree items."""
        self.tree.expandAll()
    
    def collapse_all(self) -> None:
        """Collapse all tree items."""
        self.tree.collapseAll()
    
    def get_selected_path(self) -> str:
        """Get the currently selected file/folder path."""
        index = self.tree.currentIndex()
        if index.isValid():
            source_index = self.filter_model.mapToSource(index)
            return self.model.filePath(source_index)
        return ""
    
    def select_file(self, file_path: str) -> None:
        """Select a specific file in the tree."""
        if not self.project_root:
            return
        
        # Get model index for the file
        source_index = self.model.index(file_path)
        if source_index.isValid():
            proxy_index = self.filter_model.mapFromSource(source_index)
            self.tree.setCurrentIndex(proxy_index)
            self.tree.scrollTo(proxy_index)
    
    def set_outline(self, items) -> None:
        """Populate the outline panel from (title, line) pairs."""
        self.outline_list.clear()
        count = 0
        for title, line in items:
            item = QListWidgetItem(f"{title}   :{line}")
            item.setData(Qt.ItemDataRole.UserRole, int(line))
            self.outline_list.addItem(item)
            count += 1
        if count == 0:
            item = QListWidgetItem("No section headings detected")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.outline_list.addItem(item)
        self.outline_toggle.setText(f"▾  File Outline  ({count})")

    def _on_outline_item_clicked(self, item) -> None:
        line = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(line, int) and line > 0:
            self.outline_item_clicked.emit(line)
    
    def set_theme(self, theme: str) -> None:
        """Change the tree theme."""
        palette = get_palette(theme)
        stylesheet = qss("""
            QTreeView {
                background-color: $tree_bg;
                color: $tree_fg;
                border: none;
                outline: none;
            }
            QTreeView::item {
                padding: 4px;
            }
            QTreeView::item:selected {
                background-color: $tree_selected_bg;
                color: $tree_fg;
            }
            QTreeView::item:hover {
                background-color: $tree_hover_bg;
            }
            QToolBar {
                background-color: $tree_toolbar_bg;
                border: none;
                spacing: 4px;
            }
            QLineEdit {
                background-color: $tree_filter_bg;
                color: $tree_filter_fg;
                border: 1px solid $tree_filter_border;
                padding: 4px;
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
        """, palette)
        if palette.name == "overleaf":
            stylesheet += web_qss("""
                QToolBar#TreeToolbar {
                    background-color: $ol_sidebar_toolbar_bg;
                    border-bottom: 1px solid $ol_border;
                    min-height: 30px;
                }
                QToolBar#TreeToolbar QToolButton {
                    color: $ol_text;
                    border: none;
                    border-radius: 3px;
                    padding: 3px 6px;
                    font-size: 11px;
                }
                QToolBar#TreeToolbar QToolButton:hover {
                    background-color: $ol_header_hover;
                }
                QLineEdit#TreeFilter {
                    background-color: white;
                    color: $ol_text;
                    border: 1px solid $ol_border;
                    border-radius: 4px;
                    padding: 4px 8px;
                    margin: 6px;
                }
                QTreeView#ProjectTree {
                    background-color: $ol_sidebar_bg;
                    color: $ol_text;
                }
                QTreeView#ProjectTree::item {
                    padding: 3px 4px;
                }
                QTreeView#ProjectTree::item:selected {
                    background-color: $ol_green;
                    color: white;
                }
                QPushButton#OutlineToggle {
                    background-color: $ol_sidebar_toolbar_bg;
                    color: #475569;
                    border: none;
                    border-top: 1px solid $ol_border;
                    border-bottom: 1px solid $ol_border;
                    text-align: left;
                    padding: 6px 8px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QListWidget#OutlineList {
                    background-color: $ol_sidebar_bg;
                    color: $ol_muted;
                    border: none;
                    font-size: 11px;
                }
            """)
        self.setStyleSheet(stylesheet)

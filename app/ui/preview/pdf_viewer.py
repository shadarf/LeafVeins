"""PDF preview widget using pypdfium2 or PyMuPDF."""

import os
from pathlib import Path
from typing import Optional, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QToolBar, QSpinBox, QComboBox, QMenu, QScrollArea, QApplication, QToolButton
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QCursor, QAction
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QRect, QRectF, QSize, QPoint, QPointF, QSignalBlocker
)

from core.themes import get_palette, qss, web_qss

# Try to import PDF rendering libraries
try:
    import pypdfium2 as pdfium
    PDF_BACKEND = "pypdfium2"
except ImportError:
    try:
        import fitz  # PyMuPDF
        PDF_BACKEND = "pymupdf"
    except ImportError:
        PDF_BACKEND = None

# pypdfium2 bitmaps are BGRA/BGR in memory on Windows.  Map the reported mode
# directly to Qt so we never need PIL's shared-memory image wrapper.
_BITMAP_FORMATS = {
    "BGR": QImage.Format.Format_BGR888,
    "RGB": QImage.Format.Format_RGB888,
    "BGRA": QImage.Format.Format_ARGB32,
    "RGBA": QImage.Format.Format_RGBA8888,
    "L": QImage.Format.Format_Grayscale8,
}


class PDFPageLabel(QLabel):
    """Rendered PDF page with text selection and SyncTeX click handling."""

    clicked = pyqtSignal(QPoint)  # Click position in page coordinates
    double_clicked = pyqtSignal(QPoint)
    ctrl_clicked = pyqtSignal(QPoint)  # Ctrl+Click for inverse search
    selection_changed = pyqtSignal(str)

    def __init__(self, page_number: int, parent=None):
        super().__init__(parent)
        self.page_number = page_number
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setMinimumSize(100, 100)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self._scale = 1.0
        self._highlight_rect = None
        self._char_boxes = []  # (QRectF in page points, character)
        self._page_height = 1.0
        self._selecting = False
        self._word_selection = False
        self._select_start = None
        self._select_end = None
        self._press_pos = None

    def set_pixmap(self, pixmap: QPixmap, scale: float = 1.0) -> None:
        """Set the page pixmap and the render scale used for hit testing."""
        self._pixmap = pixmap
        self._scale = scale
        self.setScaledContents(False)
        self.setPixmap(pixmap)
        # Keep the label exactly the size of the rendered page.  Letting the
        # layout stretch it made zoomed pages look distorted.
        self.setFixedSize(pixmap.size())
        self.clear_selection()

    def set_text_layout(self, boxes, page_height: float) -> None:
        """Attach extracted character boxes (page points, top-left origin)."""
        self._char_boxes = boxes or []
        self._page_height = max(1.0, float(page_height or 1.0))
        self.update()

    def set_highlight(self, rect: Optional[QRect]) -> None:
        """Set a highlight rectangle in widget coordinates."""
        self._highlight_rect = rect
        self.update()

    def clear_highlight(self) -> None:
        """Remove the highlight rectangle."""
        self._highlight_rect = None
        self.update()

    def clear_selection(self) -> None:
        """Clear the current text selection."""
        self._selecting = False
        self._word_selection = False
        self._select_start = None
        self._select_end = None
        self.update()

    def selection_text(self) -> str:
        """Return selected characters in document order."""
        rect = self._selection_rect()
        if rect is None:
            return ""
        chars = [
            char for char_rect, char in self._char_boxes
            if self._char_to_widget(char_rect).intersects(rect)
        ]
        if self._word_selection:
            chars = [char for char in chars if char.isalnum() or char == "_"]
        return "".join(chars)

    def copy_selection(self) -> bool:
        """Copy the current selection to the clipboard."""
        text = self.selection_text()
        if not text:
            return False
        QApplication.clipboard().setText(text)
        return True

    def select_all(self) -> None:
        """Select all extractable text on this page."""
        if not self._char_boxes:
            return
        self._word_selection = False
        rects = [self._char_to_widget(r) for r, _ in self._char_boxes]
        self._select_start = QPoint(
            int(min(r.left() for r in rects)), int(min(r.top() for r in rects))
        )
        self._select_end = QPoint(
            int(max(r.right() for r in rects)), int(max(r.bottom() for r in rects))
        )
        self._emit_selection()
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        if self._highlight_rect is not None:
            painter.fillRect(self._highlight_rect, QColor(255, 196, 0, 90))
            painter.setPen(QColor(200, 130, 0, 220))
            painter.drawRect(self._highlight_rect)

        selection = self._selection_rect()
        if selection is not None:
            for char_rect, _ in self._char_boxes:
                widget_rect = self._char_to_widget(char_rect)
                if widget_rect.intersects(selection):
                    painter.fillRect(
                        widget_rect.toRect().adjusted(0, 0, 1, 1),
                        QColor(48, 122, 214, 96),
                    )
            painter.setPen(QColor(78, 150, 240, 190))
            painter.drawRect(selection.toRect())
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.position().toPoint()
        page_pos = self._map_to_page(pos)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Click remains reserved for inverse SyncTeX search.
            self.ctrl_clicked.emit(page_pos)
            return

        self._press_pos = pos
        self._select_start = pos
        self._select_end = pos
        self._selecting = True
        self._word_selection = False
        self.setFocus()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._selecting:
            self._select_end = event.position().toPoint()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            end = event.position().toPoint()
            self._select_end = end
            self._selecting = False
            moved = (
                self._press_pos is None
                or (end - self._press_pos).manhattanLength() > 3
            )
            if moved:
                self._emit_selection()
            else:
                self.clicked.emit(self._map_to_page(end))
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        self._selecting = False
        self._select_word_at(pos)
        self.double_clicked.emit(self._map_to_page(pos))
        self._emit_selection()
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            return
        if (
            event.key() == Qt.Key.Key_C
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if self.copy_selection():
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy\tCtrl+C")
        copy_action.setEnabled(bool(self.selection_text()))
        copy_action.triggered.connect(self.copy_selection)
        all_action = menu.addAction("Select All")
        all_action.triggered.connect(self.select_all)
        menu.exec(event.globalPos())

    def _emit_selection(self) -> None:
        text = self.selection_text()
        if text:
            self.selection_changed.emit(text)

    def _select_word_at(self, pos: QPoint) -> None:
        target = None
        for index, (char_rect, _) in enumerate(self._char_boxes):
            if self._char_to_widget(char_rect).contains(QPointF(pos)):
                target = index
                break
        if target is None:
            return

        self._word_selection = True

        def is_word_char(char: str) -> bool:
            return char.isalnum() or char == "_"

        start = target
        while start > 0 and is_word_char(self._char_boxes[start - 1][1]):
            start -= 1
        end = target
        while (
            end < len(self._char_boxes) - 1
            and is_word_char(self._char_boxes[end + 1][1])
        ):
            end += 1

        first = self._char_to_widget(self._char_boxes[start][0])
        last = self._char_to_widget(self._char_boxes[end][0])
        self._select_start = QPoint(int(first.left()), int(first.top()))
        self._select_end = QPoint(int(last.right()), int(last.bottom()))

    def _selection_rect(self) -> Optional[QRectF]:
        if self._select_start is None or self._select_end is None:
            return None
        x1, y1 = self._select_start.x(), self._select_start.y()
        x2, y2 = self._select_end.x(), self._select_end.y()
        return QRectF(
            min(x1, x2) - 1,
            min(y1, y2) - 3,
            abs(x2 - x1) + 2,
            max(6, abs(y2 - y1) + 6),
        )

    def _pixmap_offsets(self) -> Tuple[int, int]:
        if not hasattr(self, "_pixmap") or self._pixmap.isNull():
            return 0, 0
        return (
            (self.width() - self._pixmap.width()) // 2,
            (self.height() - self._pixmap.height()) // 2,
        )

    def _char_to_widget(self, rect: QRectF) -> QRectF:
        x_offset, y_offset = self._pixmap_offsets()
        scale = self._scale or 1.0
        return QRectF(
            x_offset + rect.left() * scale,
            y_offset + rect.top() * scale,
            rect.width() * scale,
            rect.height() * scale,
        )

    def _map_to_page(self, widget_pos: QPoint) -> QPoint:
        """Map widget coordinates to page coordinates."""
        if not hasattr(self, '_pixmap') or self._pixmap.isNull():
            return widget_pos

        x_offset, y_offset = self._pixmap_offsets()
        page_x = widget_pos.x() - x_offset
        page_y = widget_pos.y() - y_offset

        if self._scale > 0:
            page_x = int(page_x / self._scale)
            page_y = int(page_y / self._scale)

        return QPoint(page_x, page_y)


class PDFViewer(QWidget):
    """PDF viewer with zoom, navigation, and SyncTeX support."""
    
    # Signals
    page_changed = pyqtSignal(int)  # Current page number (1-based)
    inverse_search_requested = pyqtSignal(int, QPoint)  # page, position
    forward_search_requested = pyqtSignal(int)  # line number
    compile_requested = pyqtSignal()
    logs_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.pdf_document = None
        self.current_page = 0
        self.total_pages = 0
        self.zoom_level = 100
        self._scale = 1.0
        self._fit_mode = None
        self._updating_zoom = False
        self._rerender_timer = QTimer(self)
        self._rerender_timer.setSingleShot(True)
        self._rerender_timer.timeout.connect(self._rerender_visible_pages)
        self._base_pixmaps = {}
        self._page_text_cache = {}
        self._page_sizes = {}
        self.page_labels = []
        self.pdf_path = None
        self.theme = "dark"
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(self.toolbar.iconSize())

        self.recompile_btn = QToolButton()
        self.recompile_btn.setText("↻  Recompile")
        self.recompile_btn.setObjectName("RecompileButton")
        self.recompile_btn.clicked.connect(self.compile_requested.emit)
        self.toolbar.addWidget(self.recompile_btn)

        self.logs_btn = QToolButton()
        self.logs_btn.setText("Logs")
        self.logs_btn.setObjectName("LogsButton")
        self.logs_btn.clicked.connect(self.logs_requested.emit)
        self.toolbar.addWidget(self.logs_btn)
        self.toolbar.addSeparator()

        # Navigation
        self.prev_page_action = self.toolbar.addAction("Previous")
        self.prev_page_action.triggered.connect(self.prev_page)
        
        self.next_page_action = self.toolbar.addAction("Next")
        self.next_page_action.triggered.connect(self.next_page)
        
        self.toolbar.addSeparator()
        
        # Page indicator
        self.page_label = QLabel("Page: - / -")
        self.toolbar.addWidget(self.page_label)
        
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        self.toolbar.addWidget(self.page_spin)
        
        self.toolbar.addSeparator()
        
        # Zoom
        self.zoom_out_action = self.toolbar.addAction("Zoom Out")
        self.zoom_out_action.triggered.connect(self.zoom_out)
        
        self.zoom_in_action = self.toolbar.addAction("Zoom In")
        self.zoom_in_action.triggered.connect(self.zoom_in)
        
        self.toolbar.addSeparator()
        
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "Fit Width", "Fit Page"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        self.toolbar.addWidget(self.zoom_combo)
        
        self.toolbar.addSeparator()
        
        # SyncTeX
        self.sync_action = QAction("SyncTeX: Off", self)
        self.sync_action.setCheckable(True)
        self.sync_action.toggled.connect(self._on_sync_toggled)
        self.toolbar.addAction(self.sync_action)
        
        layout.addWidget(self.toolbar)
        
        # Scroll area for pages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        
        # Container for pages
        self.pages_container = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_container)
        self.pages_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.pages_layout.setSpacing(10)
        self.pages_layout.setContentsMargins(20, 20, 20, 20)
        
        self.scroll_area.setWidget(self.pages_container)
        layout.addWidget(self.scroll_area)

        self.page_pill = QLabel("Page: - / -", self)
        self.page_pill.setObjectName("PagePill")
        self.page_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_pill.raise_()

        # Connect scroll for lazy loading
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def resizeEvent(self, event) -> None:
        """Keep the floating page indicator centred above the pages."""
        super().resizeEvent(event)
        if hasattr(self, "page_pill"):
            self.page_pill.adjustSize()
            x = (self.width() - self.page_pill.width()) // 2
            self.page_pill.move(x, self.toolbar.height() + 8)
    
    def load_pdf(self, pdf_path: str) -> bool:
        """Load a PDF file."""
        if not PDF_BACKEND:
            self._show_error("PDF backend not available. Install pypdfium2 or pymupdf.")
            return False
        
        path = Path(pdf_path)
        if not path.exists():
            self._show_error(f"PDF file not found: {pdf_path}")
            return False
        
        # Release the previous document and every cached render before loading a
        # new one; stale pixmaps and native document handles are a crash risk.
        if self.pdf_document is not None:
            try:
                self.pdf_document.close()
            except Exception:
                pass
            self.pdf_document = None
        self._base_pixmaps.clear()
        self._page_text_cache.clear()
        self._page_sizes.clear()

        try:
            if PDF_BACKEND == "pypdfium2":
                self.pdf_document = pdfium.PdfDocument(str(path))
            else:
                self.pdf_document = fitz.open(str(path))
            
            self.pdf_path = str(path)
            self.total_pages = len(self.pdf_document)
            self.current_page = 0
            
            # Update UI
            self.page_spin.setRange(1, self.total_pages)
            self.page_spin.setValue(1)
            self._update_page_label()
            
            # Clear existing pages
            self._clear_pages()
            
            # Render first few pages
            self._render_pages(0, min(3, self.total_pages))
            
            self.page_changed.emit(1)
            return True
            
        except Exception as e:
            self._show_error(f"Failed to load PDF: {e}")
            return False
    
    def _clear_pages(self) -> None:
        """Remove page labels from the layout immediately before deleting them."""
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                try:
                    widget.clicked.disconnect()
                    widget.double_clicked.disconnect()
                    widget.ctrl_clicked.disconnect()
                    widget.selection_changed.disconnect()
                except (TypeError, RuntimeError):
                    pass
                widget.setParent(None)
                widget.deleteLater()
        self.page_labels = []
    
    def _render_pages(self, start: int, end: int) -> None:
        """Render pages from start to end (inclusive)."""
        if not self.pdf_document:
            return
        
        for page_num in range(start, end + 1):
            if page_num >= self.total_pages:
                break
            
            # Check if already rendered
            existing = None
            for label in self.page_labels:
                if label.page_number == page_num:
                    existing = label
                    break
            
            if existing:
                continue
            
            # Render page
            pixmap = self._render_page(page_num)
            if pixmap:
                label = PDFPageLabel(page_num)
                label.set_pixmap(pixmap, self._scale)
                size = self._page_size_points(page_num)
                label.set_text_layout(
                    self._extract_page_text(page_num),
                    size[1] if size else 842.0,
                )
                label.clicked.connect(self._on_page_clicked)
                label.double_clicked.connect(self._on_page_double_clicked)
                label.ctrl_clicked.connect(
                    lambda pos, page=page_num: self._on_page_ctrl_clicked(page, pos)
                )
                self.pages_layout.addWidget(label)
                self.page_labels.append(label)

        self._update_container_width()
    
    def _update_container_width(self) -> None:
        """Ensure wide pages create a scrollbar instead of squeezing the layout."""
        if not self.page_labels:
            return
        widest = max(label.pixmap().width() for label in self.page_labels
                     if label.pixmap() and not label.pixmap().isNull())
        margins = self.pages_layout.contentsMargins()
        self.pages_container.setMinimumWidth(
            widest + margins.left() + margins.right()
        )
    
    def _target_render_scale(self) -> float:
        """Render once at 200% and scale down for normal zoom levels."""
        return max(2.0, self.zoom_level / 100.0)

    def _render_base_page(self, page_num: int, render_scale: float) -> Optional[QPixmap]:
        """Render a page natively into a QPixmap that owns its own pixels."""
        page = None
        bitmap = None
        try:
            if PDF_BACKEND == "pypdfium2":
                page = self.pdf_document[page_num]
                bitmap = page.render(scale=render_scale, rotation=0)

                image_format = _BITMAP_FORMATS.get(bitmap.mode)
                if image_format is None:
                    raise ValueError(f"Unsupported bitmap mode: {bitmap.mode}")

                # bitmap.buffer is owned by the native bitmap.  Copy it into a
                # QImage before either bitmap or page is released.  The old
                # to_pil() path left PIL pointing at freed memory and crashed.
                raw = bytes(bitmap.buffer)
                qimage = QImage(
                    raw, bitmap.width, bitmap.height, bitmap.stride, image_format
                ).copy()
                if qimage.isNull():
                    return None
                return QPixmap.fromImage(qimage)

            # PyMuPDF
            page = self.pdf_document[page_num]
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride,
                QImage.Format.Format_RGB888
            ).copy()
            return QPixmap.fromImage(img)

        except Exception as e:
            print(f"Failed to render page {page_num}: {e}")
            return None
        finally:
            if bitmap is not None:
                try:
                    bitmap.close()
                except Exception:
                    pass
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    def _render_page(self, page_num: int) -> Optional[QPixmap]:
        """Return the page at the current display zoom, using a cached render."""
        if not self.pdf_document:
            return None

        render_scale = self._target_render_scale()
        key = (page_num, round(render_scale, 2))
        base = self._base_pixmaps.get(key)
        if base is None:
            base = self._render_base_page(page_num, render_scale)
            if base is None:
                return None
            self._base_pixmaps[key] = base

        size = self._page_size_points(page_num)
        if not size:
            return base

        target = QSize(
            max(1, round(size[0] * self._scale)),
            max(1, round(size[1] * self._scale)),
        )
        if target == base.size():
            return base

        # Qt-side scaling is stable and keeps the page proportions intact.
        return base.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    
    def _page_size_points(self, page_num: int = 0) -> Optional[Tuple[float, float]]:
        """Return cached page width/height in PDF points."""
        if page_num in self._page_sizes:
            return self._page_sizes[page_num]
        if not self.pdf_document or not (0 <= page_num < self.total_pages):
            return None
        page = None
        try:
            page = self.pdf_document[page_num]
            if PDF_BACKEND == "pypdfium2":
                size = tuple(float(v) for v in page.get_size())
            else:
                rect = page.rect
                size = (float(rect.width), float(rect.height))
            self._page_sizes[page_num] = size
            return size
        except Exception as e:
            print(f"Failed to read page size: {e}")
            return None
        finally:
            if page is not None and PDF_BACKEND == "pypdfium2":
                try:
                    page.close()
                except Exception:
                    pass

    def _extract_page_text(self, page_num: int) -> list:
        """Return character boxes in page points with a top-left origin."""
        if page_num in self._page_text_cache:
            return self._page_text_cache[page_num]

        boxes = []
        page = None
        textpage = None
        try:
            if PDF_BACKEND == "pypdfium2":
                page = self.pdf_document[page_num]
                size = self._page_size_points(page_num)
                height = size[1] if size else 1.0
                textpage = page.get_textpage()
                for index in range(textpage.count_chars()):
                    char = textpage.get_text_range(index, 1)
                    if not char:
                        continue
                    left, bottom, right, top = textpage.get_charbox(index, loose=True)
                    boxes.append((
                        QRectF(
                            left,
                            height - top,
                            max(0.1, right - left),
                            max(0.1, top - bottom),
                        ),
                        char,
                    ))
            else:
                page = self.pdf_document[page_num]
                raw = page.get_text("rawdict")
                for block in raw.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            for item in span.get("chars", []):
                                char = item.get("c", "")
                                if not char:
                                    continue
                                x0, y0, x1, y1 = item["bbox"]
                                boxes.append((
                                    QRectF(x0, y0, max(0.1, x1 - x0), max(0.1, y1 - y0)),
                                    char,
                                ))
        except Exception as e:
            print(f"Failed to extract text from page {page_num}: {e}")
        finally:
            if textpage is not None:
                try:
                    textpage.close()
                except Exception:
                    pass
            if page is not None and PDF_BACKEND == "pypdfium2":
                try:
                    page.close()
                except Exception:
                    pass

        self._page_text_cache[page_num] = boxes
        return boxes
    
    def _on_scroll(self, value: int) -> None:
        """Handle scroll for lazy page loading."""
        # Check if we need to load more pages
        scroll_bar = self.scroll_area.verticalScrollBar()
        if value >= scroll_bar.maximum() - 100:
            # Near bottom, load more pages
            last_rendered = max((l.page_number for l in self.page_labels), default=-1)
            if last_rendered < self.total_pages - 1:
                next_start = last_rendered + 1
                next_end = min(next_start + 2, self.total_pages - 1)
                self._render_pages(next_start, next_end)
    
    def _update_page_label(self) -> None:
        """Update page indicator."""
        text = f"Page: {self.current_page + 1} / {self.total_pages}"
        self.page_label.setText(text)
        self.page_pill.setText(text)
        self.page_pill.adjustSize()
        self.page_pill.move(
            (self.width() - self.page_pill.width()) // 2,
            self.toolbar.height() + 8,
        )
    
    def _on_page_spin_changed(self, value: int) -> None:
        """Handle page spin box change."""
        self.go_to_page(value - 1)
    
    def _on_zoom_changed(self, text: str) -> None:
        """Handle zoom level change without recursing into our own updates."""
        if self._updating_zoom:
            return
        if text == "Fit Width":
            self.fit_width()
        elif text == "Fit Page":
            self.fit_page()
        else:
            try:
                self.set_zoom(int(text.replace('%', '')))
            except ValueError:
                pass
    
    def _on_sync_toggled(self, checked: bool) -> None:
        """Handle SyncTeX toggle."""
        self.sync_action.setText(f"SyncTeX: {'On' if checked else 'Off'}")
    
    def _on_page_clicked(self, pos: QPoint) -> None:
        """Handle page click for inverse search when SyncTeX mode is on."""
        if self.sync_action.isChecked():
            self.inverse_search_requested.emit(self.current_page + 1, pos)

    def _on_page_ctrl_clicked(self, page: int, pos: QPoint) -> None:
        """Ctrl+Click always triggers inverse search, regardless of the toggle."""
        self.inverse_search_requested.emit(page + 1, pos)
    
    def _on_page_double_clicked(self, pos: QPoint) -> None:
        """Handle page double-click."""
        pass
    
    # Navigation methods
    def go_to_page(self, page: int) -> None:
        """Go to a specific page (0-based)."""
        if 0 <= page < self.total_pages:
            self.current_page = page
            self.page_spin.setValue(page + 1)
            self._update_page_label()

            # Make sure the target page exists before scrolling to it.
            last_rendered = max((l.page_number for l in self.page_labels), default=-1)
            if page > last_rendered:
                self._render_pages(last_rendered + 1, page)

            # Scroll to page
            for label in self.page_labels:
                if label.page_number == page:
                    self.scroll_area.ensureWidgetVisible(label)
                    break
            
            self.page_changed.emit(page + 1)
    
    def next_page(self) -> None:
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.current_page + 1)
    
    def prev_page(self) -> None:
        """Go to previous page."""
        if self.current_page > 0:
            self.go_to_page(self.current_page - 1)
    
    # Zoom methods
    def _apply_zoom(self, zoom: int, label: Optional[str] = None) -> None:
        """Apply a zoom value and keep the combo box in sync safely."""
        zoom = max(10, min(500, int(zoom)))
        self.zoom_level = zoom
        self._scale = zoom / 100.0
        self._fit_mode = label

        # Assigning the combo text emits currentTextChanged.  Block it so a
        # Fit Width/Page selection cannot recurse back into itself.
        blocker = QSignalBlocker(self.zoom_combo)
        try:
            self.zoom_combo.setCurrentText(label or f"{zoom}%")
        finally:
            blocker.unblock()

        # Coalesce rapid zoom button clicks into a single rerender.
        self._rerender_timer.start(0)

    def set_zoom(self, zoom: int) -> None:
        """Set zoom level (percentage)."""
        self._apply_zoom(zoom)
    
    def zoom_in(self) -> None:
        """Increase zoom."""
        self.set_zoom(self.zoom_level + 25)
    
    def zoom_out(self) -> None:
        """Decrease zoom."""
        self.set_zoom(self.zoom_level - 25)
    
    def fit_width(self) -> None:
        """Scale the page so its width fits the preview viewport."""
        size = self._page_size_points()
        if not size or size[0] <= 0:
            return
        margins = self.pages_layout.contentsMargins()
        available = (
            self.scroll_area.viewport().width()
            - margins.left() - margins.right() - 2
        )
        if available <= 0:
            return
        self._apply_zoom(int(available / size[0] * 100), "Fit Width")
    
    def fit_page(self) -> None:
        """Scale the page so the whole page fits the preview viewport."""
        size = self._page_size_points()
        if not size or size[0] <= 0 or size[1] <= 0:
            return
        margins = self.pages_layout.contentsMargins()
        available_w = (
            self.scroll_area.viewport().width()
            - margins.left() - margins.right() - 2
        )
        available_h = (
            self.scroll_area.viewport().height()
            - margins.top() - margins.bottom() - 2
        )
        if available_w <= 0 or available_h <= 0:
            return
        zoom = min(available_w / size[0], available_h / size[1]) * 100
        self._apply_zoom(int(zoom), "Fit Page")
    
    def _rerender_visible_pages(self) -> None:
        """Resize already-loaded pages at the new zoom without recreating them."""
        if not self.page_labels:
            if self.total_pages > 0:
                self._render_pages(0, min(3, self.total_pages - 1))
            return

        scroll_bar = self.scroll_area.verticalScrollBar()
        old_max = scroll_bar.maximum()
        ratio = scroll_bar.value() / old_max if old_max > 0 else 0.0

        # Lazy-loading reacts to scrollbar changes; suppress it while resizing.
        scroll_bar.blockSignals(True)
        try:
            for label in self.page_labels:
                pixmap = self._render_page(label.page_number)
                if pixmap is None:
                    continue
                label.clear_highlight()
                label.set_pixmap(pixmap, self._scale)
                size = self._page_size_points(label.page_number)
                label.set_text_layout(
                    self._extract_page_text(label.page_number),
                    size[1] if size else 842.0,
                )
            self._update_container_width()
            scroll_bar.setValue(int(ratio * scroll_bar.maximum()))
        finally:
            scroll_bar.blockSignals(False)
    
    # SyncTeX methods
    def forward_search(self, line: int, file_path: str) -> None:
        """Forward search: editor line -> PDF position."""
        # This would require parsing .synctex.gz file
        # For now, just emit signal
        self.forward_search_requested.emit(line)
    
    def highlight_position(self, page: int, rect: QRect) -> None:
        """Highlight a PDF-point rectangle on a page (page is 1-based)."""
        target = page - 1
        if target < 0 or target >= self.total_pages:
            return

        last_rendered = max((l.page_number for l in self.page_labels), default=-1)
        if target > last_rendered:
            self._render_pages(last_rendered + 1, target)

        scaled = QRect(
            int(rect.x() * self._scale),
            int(rect.y() * self._scale),
            max(2, int(rect.width() * self._scale)),
            max(2, int(rect.height() * self._scale)),
        )
        for label in self.page_labels:
            if label.page_number == target:
                label.set_highlight(scaled)
                self.scroll_area.ensureWidgetVisible(label)
                QTimer.singleShot(2500, label.clear_highlight)
                break
    
    def _show_error(self, message: str) -> None:
        """Show error in the viewer."""
        self._clear_pages()
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet(
            f"color: {get_palette(self.theme).log_error}; padding: 20px;"
        )
        self.pages_layout.addWidget(error_label)
    
    def set_theme(self, theme: str) -> None:
        """Change the viewer theme."""
        self.theme = theme
        palette = get_palette(theme)
        stylesheet = qss("""
            QWidget {
                background-color: $pdf_bg;
                color: $pdf_widget_fg;
            }
            QToolBar {
                background-color: $pdf_toolbar_bg;
                border: none;
                spacing: 4px;
            }
            QSpinBox, QComboBox {
                background-color: $pdf_widget_bg;
                color: $pdf_widget_fg;
                border: 1px solid $pdf_widget_border;
                padding: 2px 4px;
            }
            QScrollArea {
                border: none;
                background-color: $pdf_scroll_bg;
            }
            QLabel {
                background-color: $pdf_page_bg;
                border: 1px solid $pdf_page_border;
            }
        """, palette)
        if palette.name == "overleaf":
            stylesheet += web_qss("""
                QToolBar {
                    min-height: 36px;
                    border-bottom: 1px solid $ol_border;
                }
                QToolButton#RecompileButton {
                    background-color: $ol_green;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 5px 12px;
                    font-weight: 700;
                }
                QToolButton#RecompileButton:hover {
                    background-color: $ol_green_hover;
                }
                QToolButton#LogsButton {
                    background-color: white;
                    color: $ol_text;
                    border: 1px solid $ol_border;
                    border-radius: 3px;
                    padding: 5px 10px;
                    font-weight: 600;
                }
                QLabel#PagePill {
                    background-color: rgba(30, 41, 59, 220);
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 3px 12px;
                    font-size: 11px;
                }
                QScrollArea { background-color: $ol_pdf_bg; }
                PDFPageLabel {
                    background-color: white;
                    border: 1px solid $ol_border;
                }
            """)
        self.setStyleSheet(stylesheet)
    def closeEvent(self, event) -> None:
        """Clean up on close."""
        if self.pdf_document:
            if PDF_BACKEND == "pypdfium2":
                self.pdf_document.close()
            else:
                self.pdf_document.close()
        super().closeEvent(event)
#!/usr/bin/env python3
"""InkClip - a fast scratchpad drawing app for Linux.

Draw something, hit Ctrl+C, paste it wherever you need it.

Run with:
    python main.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QMainWindow,
    QMenu,
    QScrollArea,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
)

# --- Tools -------------------------------------------------------------------

TOOL_PEN = "pen"
TOOL_HIGHLIGHTER = "highlighter"
TOOL_ERASER = "eraser"
TOOL_SELECT = "select"

TOOL_LABELS = {
    TOOL_PEN: "Pen",
    TOOL_HIGHLIGHTER: "Highlighter",
    TOOL_ERASER: "Eraser",
    TOOL_SELECT: "Select",
}

# Base stroke widths; each tool scales these (see DrawingCanvas.stroke_width).
BRUSH_SIZES = {
    "small": 2,
    "medium": 5,
    "large": 10,
    "xlarge": 20,
}
SIZE_LABELS = {
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
    "xlarge": "X-Large",
}
# Compact toolbar captions so every button (Copy especially) fits at 1000px.
SIZE_BUTTON_LABELS = {"small": "S", "medium": "M", "large": "L", "xlarge": "XL"}

# Highlighters are wide and see-through; erasers just need to be chunky.
HIGHLIGHTER_WIDTH_FACTOR = 4.0
HIGHLIGHTER_OPACITY = 0.35
ERASER_WIDTH_FACTOR = 4.0

PALETTE = [
    ("Black", "#000000"),
    ("Red", "#e02020"),
    ("Blue", "#1a5fd0"),
    ("Green", "#128a3c"),
    ("Yellow", "#f2c200"),
    ("Purple", "#8a2be2"),
]

HIGHLIGHTER_DEFAULT_COLOR = QColor("#f2e600")  # yellow
UNDO_LIMIT = 30

# Canvas sizes offered in the Canvas menu. None means "follow the window".
CANVAS_PRESETS = [
    ("Fit to window", None),
    ("800 x 600", (800, 600)),
    ("1280 x 720", (1280, 720)),
    ("1920 x 1080", (1920, 1080)),
]
CANVAS_MIN = 64
CANVAS_MAX = 8192
QWIDGETSIZE_MAX = 16777215  # Qt's "no maximum" sentinel

# Breathing room left around the drawing when selecting just the content.
CONTENT_MARGIN = 4

# A pasted image is scaled down if it would not otherwise fit on the canvas.
PASTE_FIT_MARGIN = 8

# Marching-ants animation around a selection.
ANTS_INTERVAL_MS = 110
ANTS_DASH = 4


class DrawingCanvas(QWidget):
    """White canvas backed by a QImage that persists strokes as they are drawn.

    Pen and eraser strokes are painted straight onto the backing image. The
    highlighter instead accumulates the in-progress stroke on a transparent
    overlay and composites it once on release, so a stroke that crosses itself
    stays evenly translucent instead of stacking up into a solid line.

    The canvas either follows the window ("fit to window", the default) or has a
    fixed pixel size set from the Canvas menu. A fixed canvas maps 1:1 to output
    pixels, so a 1920x1080 canvas copies and saves as exactly 1920x1080.

    The select tool drags out a rectangle; copy and save then act on that region
    instead of the whole canvas.

    A pasted image floats above the canvas until it is committed, so it can be
    dragged into place first. Anything that would otherwise read a half-placed
    canvas - copy, save, undo, clear, a new stroke - commits it first.
    """

    status_message = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_StaticContents)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setCursor(Qt.CrossCursor)
        self.setTabletTracking(False)

        self.tool = TOOL_PEN
        self.color = QColor("#000000")
        self.size_key = "medium"

        # None = follow the window; a QSize = fixed canvas of exactly that many pixels.
        self.fixed_size: QSize | None = None
        # Selected region in canvas coordinates, or None when nothing is selected.
        self.selection: QRect | None = None

        self._image = self._new_image(self.size())
        self._overlay: QImage | None = None
        self._drawing = False
        self._selecting = False
        self._selection_origin = QPointF()
        self._last_point = QPointF()
        self._undo_stack: list[QImage] = []

        # A pasted image floating above the canvas, not yet committed to it.
        self._pasted: QImage | None = None
        self._paste_rect = QRect()
        self._paste_grab: QPoint | None = None

        # Marching ants around the selection.
        self._ants_offset = 0
        self._ants_timer = QTimer(self)
        self._ants_timer.setInterval(ANTS_INTERVAL_MS)
        self._ants_timer.timeout.connect(self._advance_ants)

    # --- image helpers -------------------------------------------------------

    def _dpr(self) -> float:
        return float(self.devicePixelRatioF() or 1.0)

    def _image_dpr(self) -> float:
        """Scale factor of the backing image.

        A fixed canvas is defined in output pixels, so it stays at 1.0 and a
        1920x1080 canvas really does copy as 1920x1080. A fit-to-window canvas
        follows the screen instead, which keeps strokes crisp on HiDPI displays.
        """
        return 1.0 if self.fixed_size is not None else self._dpr()

    def _new_image(self, size) -> QImage:
        """Create a white backing image sized for the current device pixel ratio."""
        dpr = self._image_dpr()
        width = max(1, int(size.width() * dpr))
        height = max(1, int(size.height() * dpr))
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.white)
        return image

    def canvas_rect(self) -> QRect:
        """The drawable area in canvas coordinates."""
        if self.fixed_size is not None:
            return QRect(QPoint(0, 0), self.fixed_size)
        return QRect(0, 0, max(1, self.width()), max(1, self.height()))

    def _reshape_image(self) -> None:
        """Resize the backing image to match the canvas, keeping what is drawn."""
        dpr = self._image_dpr()
        if self.fixed_size is not None:
            target = QSize(self.fixed_size)
        else:
            target = QSize(
                max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))
            )
            # Fit-to-window only ever grows, so shrinking the window keeps the art.
            target = target.expandedTo(self._image.size())

        same_dpr = abs(self._image.devicePixelRatio() - dpr) < 1e-6
        if target == self._image.size() and same_dpr:
            return

        grown = QImage(target, QImage.Format_ARGB32_Premultiplied)
        grown.setDevicePixelRatio(dpr)
        grown.fill(Qt.white)
        painter = QPainter(grown)
        painter.drawImage(QPoint(0, 0), self._image)
        painter.end()
        self._image = grown

    def stroke_width(self) -> float:
        base = BRUSH_SIZES[self.size_key]
        if self.tool == TOOL_HIGHLIGHTER:
            return base * HIGHLIGHTER_WIDTH_FACTOR
        if self.tool == TOOL_ERASER:
            return base * ERASER_WIDTH_FACTOR
        return float(base)

    def stroke_color(self) -> QColor:
        if self.tool == TOOL_ERASER:
            return QColor(Qt.white)
        return QColor(self.color)

    def canvas_image(self, region: QRect | None = None) -> QImage:
        """The canvas (or just `region`) as a standalone image, for copy / save."""
        # Copying or saving means "what I can see", so a floating paste counts.
        self.commit_paste()
        dpr = self._image_dpr()
        rect = self.canvas_rect()
        if region is not None and not region.isEmpty():
            clipped = region.intersected(rect)
            if not clipped.isEmpty():
                rect = clipped

        # Canvas coordinates -> pixels in the backing image.
        pixels = QRect(
            int(rect.x() * dpr),
            int(rect.y() * dpr),
            max(1, int(rect.width() * dpr)),
            max(1, int(rect.height() * dpr)),
        ).intersected(QRect(0, 0, self._image.width(), self._image.height()))

        image = self._image.copy(pixels)
        image.setDevicePixelRatio(dpr)
        return image

    # --- state ---------------------------------------------------------------

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool == TOOL_HIGHLIGHTER:
            self.color = QColor(HIGHLIGHTER_DEFAULT_COLOR)

    def set_color(self, color: QColor) -> None:
        self.color = QColor(color)
        # Picking a color while erasing or selecting implies you want to draw.
        if self.tool in (TOOL_ERASER, TOOL_SELECT):
            self.tool = TOOL_PEN

    def set_size(self, size_key: str) -> None:
        self.size_key = size_key

    def set_canvas_size(self, size: QSize | None) -> None:
        """Fix the canvas at `size` pixels, or pass None to follow the window."""
        self.commit_paste()
        self.fixed_size = QSize(size) if size is not None else None
        if self.fixed_size is None:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        else:
            self.setFixedSize(self.fixed_size)
        self._reshape_image()
        self._selecting = False
        self.clear_selection()
        self.update()

    # --- selection -----------------------------------------------------------

    def content_rect(self) -> QRect | None:
        """Bounding box of everything drawn, or None if the canvas is blank.

        Works on the raw image buffer rather than per-pixel calls: a white pixel
        is always four 0xff bytes, so a row of untouched canvas compares equal to
        a run of 0xff, and stripping that run off each end of a row gives the
        first and last touched pixel in it. Scanning 1920x1080 costs a few ms.
        """
        image = self._image
        if image.format() != QImage.Format_ARGB32_Premultiplied:
            image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)

        dpr = self._image_dpr()
        area = self.canvas_rect()
        width = min(image.width(), max(0, int(area.width() * dpr)))
        height = min(image.height(), max(0, int(area.height() * dpr)))
        if width <= 0 or height <= 0:
            return None

        buffer = memoryview(image.constBits())
        stride = image.bytesPerLine()
        row_bytes = width * 4
        blank_row = b"\xff" * row_bytes

        top = bottom = None
        left, right = row_bytes, -1
        for y in range(height):
            start = y * stride
            row = bytes(buffer[start : start + row_bytes])
            if row == blank_row:
                continue
            lead = row_bytes - len(row.lstrip(b"\xff"))
            trail = row_bytes - len(row.rstrip(b"\xff"))
            left = min(left, lead)
            right = max(right, row_bytes - trail - 1)
            if top is None:
                top = y
            bottom = y

        if top is None:
            return None

        # Byte offsets -> pixels -> canvas coordinates.
        x0, x1 = left // 4, right // 4
        rect = QRect(
            int(x0 / dpr),
            int(top / dpr),
            max(1, math.ceil((x1 + 1) / dpr) - int(x0 / dpr)),
            max(1, math.ceil((bottom + 1) / dpr) - int(top / dpr)),
        )
        return rect.intersected(area)

    def select_content(self) -> bool:
        """Select just the drawn area. Returns False when the canvas is blank."""
        # A floating paste is part of the picture as far as the eye is concerned.
        self.commit_paste()
        rect = self.content_rect()
        if rect is None:
            self.clear_selection()
            return False
        self.set_selection(
            rect.adjusted(-CONTENT_MARGIN, -CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN)
        )
        return True

    def select_all(self) -> None:
        self.commit_paste()
        self.set_selection(self.canvas_rect())

    def set_selection(self, rect: QRect | None) -> None:
        if rect is None or rect.isEmpty():
            self.clear_selection()
            return
        self.selection = rect.intersected(self.canvas_rect())
        if self.selection.isEmpty():
            self.clear_selection()
            return
        if not self._ants_timer.isActive():
            self._ants_timer.start()
        self.update()

    def clear_selection(self) -> None:
        had_selection = self.selection is not None
        self.selection = None
        self._ants_timer.stop()
        if had_selection:
            self.update()

    def _advance_ants(self) -> None:
        if self.selection is None:
            self._ants_timer.stop()
            return
        self._ants_offset = (self._ants_offset + 1) % (ANTS_DASH * 2)
        self.update(self.selection.adjusted(-2, -2, 2, 2))

    def push_undo(self) -> None:
        self._undo_stack.append(self._image.copy())
        if len(self._undo_stack) > UNDO_LIMIT:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        # Undo right after a paste should take the paste back, not a stroke.
        if self.cancel_paste():
            return
        if not self._undo_stack:
            self.status_message.emit("Nothing to undo")
            return
        image = self._undo_stack.pop()
        image.setDevicePixelRatio(self._image_dpr())
        if image.size() != self._image.size():
            # The canvas was resized since this state was saved; drop the old
            # image into a correctly sized one rather than refusing to undo.
            fitted = QImage(self._image.size(), QImage.Format_ARGB32_Premultiplied)
            fitted.setDevicePixelRatio(self._image_dpr())
            fitted.fill(Qt.white)
            painter = QPainter(fitted)
            painter.drawImage(QPoint(0, 0), image)
            painter.end()
            image = fitted
        self._image = image
        self.update()
        self.status_message.emit("Undo")

    def clear(self) -> None:
        self.cancel_paste()
        self.push_undo()
        self._image.fill(Qt.white)
        self.clear_selection()
        self.update()
        self.status_message.emit("Canvas cleared")

    def delete_selection(self) -> bool:
        """Erase the selected region. Returns False when nothing is selected."""
        # Del on a floating paste means "get rid of it", not "erase underneath".
        if self.cancel_paste():
            return True
        if self.selection is None:
            return False
        rect = self.selection.intersected(self.canvas_rect())
        if rect.isEmpty():
            return False

        self.push_undo()
        painter = QPainter(self._image)
        # QPainter works in canvas coordinates here: the backing image carries its
        # own device pixel ratio, so no manual scaling is needed.
        painter.fillRect(rect, Qt.white)
        painter.end()

        # The drawing under the marquee is gone, so drop the marquee too rather
        # than leaving a stale region that a later Ctrl+C would silently copy.
        self.clear_selection()
        self.update()
        self.status_message.emit(f"Deleted {rect.width()} x {rect.height()}")
        return True

    # --- paste ---------------------------------------------------------------

    def has_floating_paste(self) -> bool:
        return self._pasted is not None

    def paste_image(self, image: QImage) -> bool:
        """Float `image` above the canvas, centred on the visible area.

        Nothing is written to the backing image yet: the paste stays draggable
        until `commit_paste` fixes it in place, so it can be nudged where you
        want it before it becomes part of the drawing.
        """
        if image.isNull():
            return False

        self.commit_paste()

        # Clipboard images arrive in device pixels. Dividing by the canvas scale
        # keeps them 1:1 in the copied/saved output rather than doubling on HiDPI.
        dpr = self._image_dpr()
        width = max(1, math.ceil(image.width() / dpr))
        height = max(1, math.ceil(image.height() / dpr))

        area = self.canvas_rect()
        scaled = False
        limit_w = max(1, area.width() - PASTE_FIT_MARGIN * 2)
        limit_h = max(1, area.height() - PASTE_FIT_MARGIN * 2)
        if width > limit_w or height > limit_h:
            factor = min(limit_w / width, limit_h / height)
            width = max(1, int(width * factor))
            height = max(1, int(height * factor))
            scaled = True

        self._pasted = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._paste_rect = self._clamp_paste(
            QRect(self._paste_origin(width, height), QSize(width, height))
        )
        self._paste_grab = None
        self.set_selection(self._paste_rect)
        self.setCursor(Qt.SizeAllCursor)
        self.update()

        note = " (scaled to fit)" if scaled else ""
        self.status_message.emit(
            f"Pasted {width} x {height}{note} - drag to move, Enter to place, Esc to cancel"
        )
        return True

    def _paste_origin(self, width: int, height: int) -> QPoint:
        """Top-left that centres a width x height paste on what you can see."""
        visible = self.visibleRegion().boundingRect()
        if visible.isEmpty():
            visible = self.canvas_rect()
        return QPoint(
            visible.x() + (visible.width() - width) // 2,
            visible.y() + (visible.height() - height) // 2,
        )

    def _clamp_paste(self, rect: QRect) -> QRect:
        """Keep a paste on the canvas, so it can never be dragged out of reach."""
        area = self.canvas_rect()
        x = min(max(rect.x(), area.left()), max(area.left(), area.right() - rect.width() + 1))
        y = min(max(rect.y(), area.top()), max(area.top(), area.bottom() - rect.height() + 1))
        return QRect(x, y, rect.width(), rect.height())

    def commit_paste(self) -> bool:
        """Draw the floating paste into the canvas. False when there is none."""
        if self._pasted is None:
            return False

        rect = QRect(self._paste_rect)
        self.push_undo()
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        # An explicit target rect scales the source for us, so the paste lands at
        # the size it was shown at regardless of the image's own pixel ratio.
        painter.drawImage(rect, self._pasted)
        painter.end()

        self._pasted = None
        self._paste_rect = QRect()
        self._paste_grab = None
        self.setCursor(Qt.CrossCursor)
        # The selection is left on the pasted region so Ctrl+C can grab just it.
        self.set_selection(rect)
        self.update()
        self.status_message.emit(f"Placed {rect.width()} x {rect.height()}")
        return True

    def cancel_paste(self) -> bool:
        """Throw the floating paste away without touching the canvas."""
        if self._pasted is None:
            return False
        stale = self._paste_rect.adjusted(-2, -2, 2, 2)
        self._pasted = None
        self._paste_rect = QRect()
        self._paste_grab = None
        self.setCursor(Qt.CrossCursor)
        self.clear_selection()
        self.update(stale)
        self.status_message.emit("Paste cancelled")
        return True

    # --- drawing -------------------------------------------------------------

    def _begin_stroke(self, point: QPointF) -> None:
        self.push_undo()
        self._drawing = True
        self._last_point = QPointF(point)
        if self.tool == TOOL_HIGHLIGHTER:
            self._overlay = QImage(self._image.size(), QImage.Format_ARGB32_Premultiplied)
            self._overlay.setDevicePixelRatio(self._image_dpr())
            self._overlay.fill(Qt.transparent)
        # A click without a drag should still leave a dot.
        self._draw_segment(point, point, 1.0)

    def _draw_segment(self, start: QPointF, end: QPointF, pressure: float) -> None:
        target = self._overlay if self.tool == TOOL_HIGHLIGHTER else self._image
        if target is None:
            return

        width = self.stroke_width()
        if self.tool == TOOL_PEN and pressure > 0.0:
            # Light pressure thins the line a little; mouse input reports 1.0.
            width *= 0.35 + 0.65 * min(pressure, 1.0)

        painter = QPainter(target)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if start == end:
            # QPainter draws nothing for a zero-length line, so a click that never
            # moves needs an explicit dot of the same diameter as the stroke.
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.stroke_color())
            painter.drawEllipse(start, width / 2.0, width / 2.0)
        else:
            pen = QPen(self.stroke_color(), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(start, end)
        painter.end()

        # Repaint just the dirty band, padded for the stroke width.
        pad = int(width) + 2
        rect = QRect(start.toPoint(), end.toPoint()).normalized().adjusted(-pad, -pad, pad, pad)
        self.update(rect)

    def _end_stroke(self) -> None:
        self._drawing = False
        if self.tool == TOOL_HIGHLIGHTER and self._overlay is not None:
            painter = QPainter(self._image)
            painter.setOpacity(HIGHLIGHTER_OPACITY)
            painter.drawImage(QPoint(0, 0), self._overlay)
            painter.end()
            self._overlay = None
            self.update()

    # --- events --------------------------------------------------------------

    def _pointer_press(self, point: QPointF) -> None:
        if self._pasted is not None:
            if self._paste_rect.contains(point.toPoint()):
                self._paste_grab = point.toPoint() - self._paste_rect.topLeft()
                return
            # Clicking away from the paste places it. The click is deliberately
            # not passed on as a stroke, so putting a paste down can never leave
            # a stray mark on the drawing.
            self.commit_paste()
            return

        if self.tool == TOOL_SELECT:
            self._selection_origin = QPointF(point)
            self.clear_selection()
            self._selecting = True
        else:
            self._begin_stroke(point)

    def _pointer_move(self, point: QPointF, pressure: float) -> None:
        if self._paste_grab is not None:
            self._move_paste(point.toPoint() - self._paste_grab)
        elif self._selecting:
            rect = self._drag_rect(point)
            if not rect.isEmpty():
                self.set_selection(rect)
        elif self._drawing:
            self._draw_segment(self._last_point, point, pressure)
            self._last_point = QPointF(point)

    def _move_paste(self, top_left: QPoint) -> None:
        """Reposition the floating paste, repainting only what actually moved."""
        moved = self._clamp_paste(QRect(top_left, self._paste_rect.size()))
        if moved == self._paste_rect:
            return
        # Repaint the union of where it was and where it is, so no ghost is left.
        stale = self._paste_rect.united(moved).adjusted(-2, -2, 2, 2)
        self._paste_rect = moved
        self.set_selection(moved)
        self.update(stale)

    def _drag_rect(self, point: QPointF) -> QRect:
        """Rectangle between the drag origin and `point`, sized by drag distance.

        QRect's two-point constructor is inclusive, which would make a 300px drag
        select 301px, so the size is computed explicitly.
        """
        origin = self._selection_origin
        left, right = sorted((origin.x(), point.x()))
        top, bottom = sorted((origin.y(), point.y()))
        return QRect(int(left), int(top), int(right - left), int(bottom - top))

    def _pointer_release(self) -> None:
        if self._paste_grab is not None:
            self._paste_grab = None
            self.status_message.emit(
                f"Paste at {self._paste_rect.x()}, {self._paste_rect.y()}"
                " - Enter to place, Esc to cancel"
            )
            return
        if self._selecting:
            self._selecting = False
            selection = self.selection
            # A click rather than a real drag means "deselect".
            if selection is None or selection.width() < 3 or selection.height() < 3:
                self.clear_selection()
                self.status_message.emit("Selection cleared")
            else:
                self.status_message.emit(
                    f"Selected {selection.width()} x {selection.height()}"
                    " - Ctrl+C to copy, Del to erase"
                )
            self.selection_changed.emit()
        elif self._drawing:
            self._end_stroke()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pointer_press(event.position())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self._pointer_move(event.position(), 1.0)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pointer_release()

    def tabletEvent(self, event) -> None:
        """Stylus support: same strokes as the mouse, plus pressure on the pen."""
        point = event.position()
        event_type = event.type()

        if event_type == QEvent.Type.TabletPress:
            self._pointer_press(point)
        elif event_type == QEvent.Type.TabletMove:
            self._pointer_move(point, event.pressure())
        elif event_type == QEvent.Type.TabletRelease:
            self._pointer_release()
        else:
            event.ignore()
            return
        event.accept()

    def resizeEvent(self, event) -> None:
        """Grow the backing image as needed, keeping whatever is already drawn."""
        if self.fixed_size is None:
            self._reshape_image()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # The painter is already clipped to event.rect(); both images carry the
        # widget's device pixel ratio, so drawing them at the origin is enough.
        painter.drawImage(QPoint(0, 0), self._image)
        if self._overlay is not None:
            painter.setOpacity(HIGHLIGHTER_OPACITY)
            painter.drawImage(QPoint(0, 0), self._overlay)
            painter.setOpacity(1.0)
        if self._pasted is not None:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(self._paste_rect, self._pasted)
        if self.selection is not None:
            self._paint_selection(painter)
        painter.end()

    def _paint_selection(self, painter: QPainter) -> None:
        """Marching ants: a white base line with a moving dark dashed line on top."""
        rect = QRect(self.selection).adjusted(0, 0, -1, -1)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawRect(rect)
        pen = QPen(QColor(20, 20, 24), 1)
        pen.setDashPattern([ANTS_DASH, ANTS_DASH])
        pen.setDashOffset(self._ants_offset)
        painter.setPen(pen)
        painter.drawRect(rect)


class CanvasSizeDialog(QDialog):
    """Two spin boxes for picking a custom canvas size."""

    def __init__(self, parent: QWidget, current: QSize) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom canvas size")

        self.width_box = QSpinBox(self)
        self.height_box = QSpinBox(self)
        for box, value in ((self.width_box, current.width()), (self.height_box, current.height())):
            box.setRange(CANVAS_MIN, CANVAS_MAX)
            box.setSuffix(" px")
            box.setValue(value)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("Width", self.width_box)
        layout.addRow("Height", self.height_box)
        layout.addRow(buttons)

    def canvas_size(self) -> QSize:
        return QSize(self.width_box.value(), self.height_box.value())


class MainWindow(QMainWindow):
    """Toolbar, canvas, status bar, and the actions that tie them together."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("InkClip")
        self.resize(1000, 700)
        self.setMinimumSize(640, 480)

        self.canvas = DrawingCanvas(self)
        self.canvas.status_message.connect(self.show_status)
        self.canvas.selection_changed.connect(self._update_mode_label)

        # A scroll area so a canvas larger than the window stays reachable.
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)  # fit-to-window by default
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setFrameShape(QFrame.NoFrame)
        viewport = self.scroll.viewport()
        palette = viewport.palette()
        palette.setColor(QPalette.Window, QColor("#d7d8dd"))
        viewport.setAutoFillBackground(True)
        viewport.setPalette(palette)
        self.setCentralWidget(self.scroll)

        self._tool_actions: dict[str, QAction] = {}
        self._size_actions: dict[str, QAction] = {}
        self._color_buttons: dict[str, QToolButton] = {}
        self._canvas_actions: list[tuple[QAction, tuple[int, int] | None]] = []
        self._canvas_label = CANVAS_PRESETS[0][0]

        self._build_toolbar()
        self._build_statusbar()
        self._build_shortcuts()

        self.select_tool(TOOL_PEN)
        self.select_size("medium")
        self.select_color(PALETTE[0][1])
        self._canvas_actions[0][0].setChecked(True)

    # --- UI construction -----------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = QToolBar("Tools", self)
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        bar.setStyleSheet(
            "QToolBar { background: #f4f4f6; border-bottom: 1px solid #d8d8de; padding: 4px; spacing: 2px; }"
            "QToolButton { padding: 5px 6px; border: 1px solid transparent; border-radius: 4px; }"
            "QToolButton:hover { background: #e4e4ea; }"
            "QToolButton:checked { background: #ffffff; border: 1px solid #9aa0aa; }"
            "QToolButton#primary { background: #1a5fd0; color: #ffffff; font-weight: bold; }"
            "QToolButton#primary:hover { background: #1750b0; }"
        )
        self.addToolBar(bar)

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)
        for tool, shortcut_hint in (
            (TOOL_PEN, "P"),
            (TOOL_HIGHLIGHTER, "H"),
            (TOOL_ERASER, "E"),
            (TOOL_SELECT, "S"),
        ):
            action = QAction(TOOL_LABELS[tool], self)
            action.setCheckable(True)
            tip = f"{TOOL_LABELS[tool]} ({shortcut_hint})"
            if tool == TOOL_SELECT:
                tip += " - drag a region, or Ctrl+A to select just the drawing"
            action.setToolTip(tip)
            action.triggered.connect(lambda _checked, t=tool: self.select_tool(t))
            tool_group.addAction(action)
            bar.addAction(action)
            self._tool_actions[tool] = action

        bar.addSeparator()

        for name, hex_color in PALETTE:
            button = QToolButton(self)
            button.setToolTip(name)
            button.setFixedSize(24, 24)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked, c=hex_color: self.select_color(c))
            self._style_color_button(button, hex_color, selected=False)
            bar.addWidget(button)
            self._color_buttons[hex_color] = button

        bar.addSeparator()

        size_group = QActionGroup(self)
        size_group.setExclusive(True)
        for index, key in enumerate(BRUSH_SIZES, start=1):
            action = QAction(SIZE_BUTTON_LABELS[key], self)
            action.setCheckable(True)
            action.setToolTip(f"{SIZE_LABELS[key]} brush ({index})")
            action.triggered.connect(lambda _checked, k=key: self.select_size(k))
            size_group.addAction(action)
            bar.addAction(action)
            self._size_actions[key] = action

        bar.addSeparator()

        # Canvas size menu.
        canvas_button = QToolButton(self)
        canvas_button.setText("Canvas")
        canvas_button.setToolTip("Canvas size")
        canvas_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(canvas_button)
        canvas_group = QActionGroup(self)
        canvas_group.setExclusive(True)
        for label, dimensions in CANVAS_PRESETS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked, d=dimensions, n=label: self.select_canvas_size(d, n)
            )
            canvas_group.addAction(action)
            menu.addAction(action)
            self._canvas_actions.append((action, dimensions))
        menu.addSeparator()
        custom = QAction("Custom...", self)
        custom.setCheckable(True)
        custom.triggered.connect(self.prompt_canvas_size)
        canvas_group.addAction(custom)
        menu.addAction(custom)
        self._custom_canvas_action = custom
        canvas_button.setMenu(menu)
        bar.addWidget(canvas_button)

        bar.addSeparator()

        for text, tooltip, handler in (
            ("Undo", "Undo (Ctrl+Z)", self.canvas.undo),
            ("Clear", "Clear canvas (C)", self.canvas.clear),
            ("Save", "Save as PNG (Ctrl+S)", self.save_png),
            ("Paste", "Paste an image from the clipboard (Ctrl+V)", self.paste_from_clipboard),
            ("Copy", "Copy canvas to clipboard (Ctrl+C)", self.copy_to_clipboard),
        ):
            action = QAction(text, self)
            action.setToolTip(tooltip)
            action.triggered.connect(handler)
            bar.addAction(action)
            if text == "Copy":
                # Copy is the whole point of InkClip, so give it some weight.
                button = bar.widgetForAction(action)
                if button is not None:
                    button.setObjectName("primary")

    def _style_color_button(self, button: QToolButton, hex_color: str, selected: bool) -> None:
        border = "2px solid #202024" if selected else "1px solid #b8b8c0"
        button.setStyleSheet(
            f"QToolButton {{ background: {hex_color}; border: {border}; border-radius: 12px; }}"
        )

    def _build_statusbar(self) -> None:
        self.mode_label = QLabel()
        self.statusBar().addPermanentWidget(self.mode_label)
        self.statusBar().showMessage("Ready - draw, then press Ctrl+C to copy")

    def _build_shortcuts(self) -> None:
        bindings = [
            (QKeySequence.Copy, self.copy_to_clipboard),
            (QKeySequence.Paste, self.paste_from_clipboard),
            (QKeySequence.Undo, self.canvas.undo),
            (QKeySequence.Save, self.save_png),
            (QKeySequence.SelectAll, self.select_content),
            ("Ctrl+Shift+A", self.select_all),
            ("P", lambda: self.select_tool(TOOL_PEN)),
            ("H", lambda: self.select_tool(TOOL_HIGHLIGHTER)),
            ("E", lambda: self.select_tool(TOOL_ERASER)),
            ("S", lambda: self.select_tool(TOOL_SELECT)),
            ("Return", self.place_paste),
            ("Enter", self.place_paste),
            ("Esc", self.deselect),
            (QKeySequence.Delete, self.delete_selection),
            ("Backspace", self.delete_selection),
            ("C", self.canvas.clear),  # plain C; Ctrl+C is matched separately
            ("1", lambda: self.select_size("small")),
            ("2", lambda: self.select_size("medium")),
            ("3", lambda: self.select_size("large")),
            ("4", lambda: self.select_size("xlarge")),
        ]
        for key, handler in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(handler)

    # --- selection -----------------------------------------------------------

    def select_tool(self, tool: str) -> None:
        self.canvas.set_tool(tool)
        self._tool_actions[tool].setChecked(True)
        if tool == TOOL_HIGHLIGHTER:
            # set_tool switched the color to yellow; reflect that in the toolbar.
            self._sync_color_buttons(self.canvas.color.name())
        self._update_mode_label()
        if tool == TOOL_SELECT:
            self.show_status(
                "Select tool - drag a region, or press Ctrl+A to select the drawing"
            )
        else:
            self.show_status(f"{TOOL_LABELS[tool]} selected")

    def select_color(self, hex_color: str) -> None:
        self.canvas.set_color(QColor(hex_color))
        self._sync_color_buttons(hex_color)
        # set_color may have flipped the eraser back to the pen.
        self._tool_actions[self.canvas.tool].setChecked(True)
        self._update_mode_label()

    def _sync_color_buttons(self, hex_color: str) -> None:
        target = QColor(hex_color).name().lower()
        for color, button in self._color_buttons.items():
            selected = QColor(color).name().lower() == target
            button.setChecked(selected)
            self._style_color_button(button, color, selected)

    def select_size(self, size_key: str) -> None:
        self.canvas.set_size(size_key)
        self._size_actions[size_key].setChecked(True)
        self._update_mode_label()

    def select_content(self) -> None:
        """Ctrl+A: select just the drawing, ignoring the blank canvas around it."""
        if not self.canvas.select_content():
            self._update_mode_label()
            self.show_status("Canvas is empty - nothing to select")
            return
        # Deliberately stays on the current tool: draw, Ctrl+A, Ctrl+C, keep drawing.
        self._update_mode_label()
        rect = self.canvas.selection
        if rect is not None:
            self.show_status(
                f"Selected the drawing ({rect.width()} x {rect.height()})"
                " - Ctrl+C to copy, Del to erase"
            )

    def select_all(self) -> None:
        """Ctrl+Shift+A: select the whole canvas, blank margins included."""
        self.canvas.select_all()
        self._update_mode_label()
        rect = self.canvas.selection
        if rect is not None:
            self.show_status(f"Selected all ({rect.width()} x {rect.height()})")

    def delete_selection(self) -> None:
        """Del / Backspace: erase whatever is inside the selection."""
        if not self.canvas.delete_selection():
            self.show_status("Nothing selected - press Ctrl+A to select the drawing")
            return
        self._update_mode_label()

    def deselect(self) -> None:
        """Esc: cancel a pending paste, or drop the selection."""
        if self.canvas.cancel_paste():
            self._update_mode_label()
            return
        if self.canvas.selection is None:
            return
        self.canvas.clear_selection()
        self._update_mode_label()
        self.show_status("Selection cleared")

    def select_canvas_size(self, dimensions, label: str) -> None:
        size = None if dimensions is None else QSize(*dimensions)
        self.canvas.set_canvas_size(size)
        # Only a fit-to-window canvas stretches with the scroll area.
        self.scroll.setWidgetResizable(size is None)
        self._canvas_label = label
        self._update_mode_label()
        self.show_status(f"Canvas: {label}")

    def prompt_canvas_size(self) -> None:
        current = self.canvas.canvas_rect().size()
        dialog = CanvasSizeDialog(self, current)
        if dialog.exec() != QDialog.Accepted:
            # Put the tick back on whichever preset is actually in effect.
            self._sync_canvas_actions()
            return
        size = dialog.canvas_size()
        label = f"{size.width()} x {size.height()}"
        self.select_canvas_size((size.width(), size.height()), label)
        self._sync_canvas_actions()

    def _sync_canvas_actions(self) -> None:
        """Tick the menu entry matching the canvas in effect (custom if no preset)."""
        current = None if self.canvas.fixed_size is None else (
            self.canvas.fixed_size.width(),
            self.canvas.fixed_size.height(),
        )
        matched = False
        for action, dimensions in self._canvas_actions:
            hit = dimensions == current
            action.setChecked(hit)
            matched = matched or hit
        self._custom_canvas_action.setChecked(not matched)

    def _update_mode_label(self) -> None:
        color_name = next(
            (name for name, value in PALETTE if QColor(value) == self.canvas.color),
            self.canvas.color.name(),
        )
        parts = [TOOL_LABELS[self.canvas.tool]]
        if self.canvas.tool != TOOL_SELECT:
            parts.append(SIZE_LABELS[self.canvas.size_key])
            if self.canvas.tool != TOOL_ERASER:
                parts.append(color_name)
        rect = self.canvas.canvas_rect()
        parts.append(f"Canvas {rect.width()} x {rect.height()}")
        if self.canvas.selection is not None:
            selection = self.canvas.selection
            parts.append(f"Selected {selection.width()} x {selection.height()}")
        self.mode_label.setText("  |  ".join(parts))

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 3000)

    # --- actions -------------------------------------------------------------

    def paste_from_clipboard(self) -> None:
        """Ctrl+V: bring an image in from the clipboard, floating until placed."""
        image = self._clipboard_image()
        if image is None:
            self.show_status(self._paste_failure_reason())
            return
        self.canvas.paste_image(image)
        self._update_mode_label()

    def _clipboard_image(self) -> QImage | None:
        """The clipboard as an image, whether it holds one or a path to one."""
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            return image

        # File managers copy a selected file as a URL rather than as pixels.
        mime = clipboard.mimeData()
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                loaded = QImage(url.toLocalFile())
                if not loaded.isNull():
                    return loaded
        return None

    def _paste_failure_reason(self) -> str:
        """Say what the clipboard actually held, rather than just 'no image'."""
        mime = QGuiApplication.clipboard().mimeData()
        if mime is not None and mime.hasText():
            return "Clipboard holds text, not an image - nothing to paste"
        return "Clipboard has no image to paste"

    def place_paste(self) -> None:
        """Enter: commit a floating paste to the canvas."""
        if self.canvas.commit_paste():
            self._update_mode_label()

    def copy_to_clipboard(self) -> None:
        """Put the canvas - or the selection, if there is one - on the clipboard."""
        selection = self.canvas.selection
        image = self.canvas.canvas_image(selection)
        clipboard = QGuiApplication.clipboard()
        clipboard.setPixmap(QPixmap.fromImage(image))
        what = "selection" if selection is not None else "canvas"
        self.show_status(
            f"Copied {what} to clipboard ({image.width()} x {image.height()})"
        )

    def save_png(self) -> None:
        title = (
            "Save selection as PNG"
            if self.canvas.selection is not None
            else "Save canvas as PNG"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, title, "inkclip.png", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if self.canvas.canvas_image(self.canvas.selection).save(path, "PNG"):
            self.show_status(f"Saved {path}")
        else:
            self.show_status(f"Failed to save {path}")


def load_app_icon() -> QIcon:
    """Use the installed hicolor icon, falling back to the one in this checkout."""
    icon = QIcon.fromTheme("inkclip")
    if icon.isNull():
        bundled = Path(__file__).resolve().parent / "packaging" / "inkclip.svg"
        if bundled.exists():
            icon = QIcon(str(bundled))
    return icon


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("InkClip")
    app.setApplicationDisplayName("InkClip")
    # Ties the window to inkclip.desktop so compositors and launchers (rofi,
    # waybar, niri) show the right name and icon for it.
    app.setDesktopFileName("inkclip")
    app.setWindowIcon(load_app_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

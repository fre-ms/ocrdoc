"""The filters of one page, checked by eye: the page as it is and as OCR will read it,
side by side, every filter switchable.

The filters change only ocrdoc's own rendering of the page, never the document
(:mod:`ocrdoc.filters`).  The panel works on a :class:`~ocrdoc.project.Project`; every
change goes into the project at once (:meth:`Project.set_filters`), which then reads the
page again when its text is needed.
"""

from __future__ import annotations

from collections.abc import Callable

from doccor.gui.view import PREVIEW_DPI, PageView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ocrdoc import filters as filtering
from ocrdoc.errors import describe_error
from ocrdoc.filters import Filters
from ocrdoc.gui.words import Words
from ocrdoc.project import Project

_SWITCHES = ("letter_mode", "remove_colour", "remove_lines", "black_white")


class FiltersPanel(QWidget):
    """The filters of the page :meth:`show_page` names."""

    changed = Signal(int)  # the filters of this page changed

    def __init__(self, project: Project, words: Words, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.w = words
        self.number = 0
        self.chosen = Filters()
        self._muted = False
        outer = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_views())
        splitter.addWidget(self._build_controls())
        splitter.setSizes([820, 320])
        outer.addWidget(splitter)

    # -- building ------------------------------------------------------------------------------
    def _build_views(self) -> QSplitter:
        """The page and what OCR reads, linked in scroll and zoom."""
        views = QSplitter(Qt.Orientation.Horizontal)
        self.page_view, self.ocr_view = PageView(), PageView()
        PageView.link(self.page_view, self.ocr_view)
        for view, title in ((self.page_view, self.w("filters_page")),
                            (self.ocr_view, self.w("filters_ocr"))):
            column = QWidget()
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title)
            label.setWordWrap(True)
            layout.addWidget(label)
            layout.addWidget(view, 1)
            views.addWidget(column)
        views.setSizes([410, 410])
        return views

    def _build_controls(self) -> QWidget:
        """The column on the right: note, filters, page buttons, zoom."""
        right = QWidget()
        r = QVBoxLayout(right)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        r.addWidget(self.note)
        group = QGroupBox(self.w("filters"))
        form = QFormLayout(group)
        self.upscaling = QComboBox()
        for factor in filtering.UPSCALE:
            self.upscaling.addItem(self.w("not") if factor == 1 else f"{factor}×", factor)
        self.upscaling.setToolTip(self.w("upscale_tip"))
        self.upscaling.currentIndexChanged.connect(lambda _i: self._from_form())
        form.addRow(self.w("upscale"), self.upscaling)
        self.boxes: dict[str, QCheckBox] = {}
        for key in _SWITCHES:
            box = QCheckBox(self.w(key))
            box.setToolTip(self.w(f"{key}_tip"))
            box.toggled.connect(lambda _on: self._from_form())
            self.boxes[key] = box
            form.addRow(box)
        r.addWidget(group)
        self.controls = group
        buttons = QVBoxLayout()
        self.page_buttons: list[QPushButton] = []
        for key, action in (("restore", self.restore), ("no_filters", self.none),
                            ("to_all", self.copy_to_all)):
            button = QPushButton(self.w(key))
            button.clicked.connect(action)
            buttons.addWidget(button)
            self.page_buttons.append(button)
        r.addLayout(buttons)
        r.addStretch(1)
        r.addLayout(self._build_zoom())
        return right

    def _build_zoom(self) -> QHBoxLayout:
        """Zoom buttons for both views."""
        zoom = QHBoxLayout()
        actions: list[tuple[str, Callable[[], None]]] = [
            ("+", lambda: self.ocr_view.zoom(1.25)), ("−", lambda: self.ocr_view.zoom(0.8)),
            (self.w("zoom_reset"), self.ocr_view.reset_zoom)]
        for text, action in actions:
            button = QPushButton(text)
            button.setMaximumWidth(48)
            button.clicked.connect(action)
            zoom.addWidget(button)
        zoom.addStretch(1)
        return zoom

    # -- the page ------------------------------------------------------------------------------
    def show_page(self, number: int) -> None:
        """Show page ``number`` with its filters."""
        self.number = number
        chosen = self.project.filters(number)
        usable = chosen is not None and filtering.available()
        self.controls.setEnabled(usable)
        for button in self.page_buttons:
            button.setEnabled(usable)
        self.chosen = chosen or Filters()
        self._to_form()
        self.draw()

    def _to_form(self) -> None:
        """Fill the form from the filters, without writing back."""
        f = self.chosen
        self._muted = True
        try:
            self.upscaling.setCurrentIndex(filtering.UPSCALE.index(f.upscale))
            for key in _SWITCHES:
                self.boxes[key].setChecked(bool(getattr(f, key)))
            self.boxes["black_white"].setEnabled(not f.letter_mode)
        finally:
            self._muted = False

    def _from_form(self) -> None:
        """Take the form into the filters and the project, and redraw."""
        if self._muted:
            return
        f = self.chosen
        f.upscale = int(self.upscaling.currentData() or 1)
        for key in _SWITCHES:
            setattr(f, key, self.boxes[key].isChecked())
        self.boxes["black_white"].setEnabled(not f.letter_mode)
        self._commit()

    def _commit(self, by_person: bool = True) -> None:
        """Hand the filters to the project, redraw, and say that they changed."""
        self.project.set_filters(self.number, self.chosen, by_person)
        self.draw()
        self.changed.emit(self.number)

    # -- actions -------------------------------------------------------------------------------
    def restore(self) -> None:
        """ocrdoc's suggestion again."""
        self.chosen = self.project.suggestion(self.number)
        self._to_form()
        self._commit(by_person=False)

    def none(self) -> None:
        """No filter: OCR reads the page as it is."""
        self.chosen = Filters()
        self._to_form()
        self._commit()

    def copy_to_all(self) -> None:
        """The filters of this page on every page OCR reads."""
        for n in range(len(self.project.pages)):
            if n != self.number and self.project.filters(n) is not None:
                self.project.set_filters(n, self.chosen)
                self.changed.emit(n)

    # -- drawing -------------------------------------------------------------------------------
    def draw(self) -> None:
        """Both views and the note."""
        n = self.number
        page = self.project.page_png(n, PREVIEW_DPI)
        self.page_view.scale_factor = PREVIEW_DPI / 72.0
        self.page_view.display(page)
        if self.project.filters(n) is None or not filtering.available():
            self.ocr_view.scale_factor = PREVIEW_DPI / 72.0
            self.ocr_view.display(page)
            self.note.setText(self.w("filters_none_needed") if filtering.available()
                              else self.w("no_opencv"))
            return
        try:
            png = self.project.preview(n, self.chosen, PREVIEW_DPI)
        except Exception as e:  # shown instead of breaking the window
            self.note.setText(self.w("failed", error=describe_error(e, self.w.language)))
            return
        image = QImage.fromData(png)
        self.ocr_view.scale_factor = image.width() / self.project.doc[n].rect.width
        self.ocr_view.set_base((PREVIEW_DPI / 72.0) / self.ocr_view.scale_factor)
        self.ocr_view.display(png)
        suggested = self.chosen == self.project.suggestion(n)
        self.note.setText(self.w("filters_suggested" if suggested else "filters_chosen",
                                 tool="ocrdoc"))

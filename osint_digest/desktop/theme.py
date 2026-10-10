"""Rounded navy themes around standard, accessible Qt controls."""
import ctypes
import os

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLayout
from osint_digest.desktop.settings import resource_path

THEMES = {
    'dark': {'background': '#071321', 'card': '#101f35', 'panel': '#142942',
             'field': '#081729', 'text': '#ecf4ff', 'muted': '#b5c6dc',
             'accent': '#7adcf5', 'on_accent': '#062239', 'border': '#6685a9',
             'focus': '#f6c453', 'error': '#ffb4b4'},
    'light': {'background': '#eef4fc', 'card': '#ffffff', 'panel': '#dceafa',
              'field': '#ffffff', 'text': '#142946', 'muted': '#3f5775',
              'accent': '#1649a9', 'on_accent': '#ffffff', 'border': '#627693',
              'focus': '#795200', 'error': '#972032'},
}


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
    values = sorted((luminance(first), luminance(second)))
    return (values[1] + .05) / (values[0] + .05)


def high_contrast_enabled():
    if os.name != 'nt':
        return False
    class HighContrast(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint), ('flags', ctypes.c_uint), ('scheme', ctypes.c_void_p)]
    value = HighContrast()
    value.size = ctypes.sizeof(value)
    return bool(ctypes.windll.user32.SystemParametersInfoW(0x42, value.size, ctypes.byref(value), 0)
                and value.flags & 1)


def windows_palette(fallback):
    """Read Windows contrast colors; never change Windows preferences."""
    palette = QPalette(fallback)
    if os.name == 'nt':
        for role, index in ((QPalette.ColorRole.Window, 5), (QPalette.ColorRole.WindowText, 8),
                            (QPalette.ColorRole.Base, 5), (QPalette.ColorRole.Text, 8),
                            (QPalette.ColorRole.Button, 15), (QPalette.ColorRole.ButtonText, 18),
                            (QPalette.ColorRole.Highlight, 13), (QPalette.ColorRole.HighlightedText, 14)):
            rgb = ctypes.windll.user32.GetSysColor(index)
            palette.setColor(role, QColor(rgb & 255, (rgb >> 8) & 255, (rgb >> 16) & 255))
    return palette


def palette_for(colors):
    p = QPalette()
    for role, token in ((QPalette.ColorRole.Window, 'background'), (QPalette.ColorRole.WindowText, 'text'),
                        (QPalette.ColorRole.Base, 'field'), (QPalette.ColorRole.AlternateBase, 'panel'),
                        (QPalette.ColorRole.Text, 'text'), (QPalette.ColorRole.Button, 'panel'),
                        (QPalette.ColorRole.ButtonText, 'text'), (QPalette.ColorRole.Highlight, 'accent'),
                        (QPalette.ColorRole.HighlightedText, 'on_accent'),
                        (QPalette.ColorRole.ToolTipBase, 'card'), (QPalette.ColorRole.ToolTipText, 'text'),
                        (QPalette.ColorRole.PlaceholderText, 'muted'), (QPalette.ColorRole.Link, 'accent')):
        p.setColor(role, QColor(colors[token]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors['muted']))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(colors['muted']))
    return p


def stylesheet(theme, base_points):
    c = THEMES[theme]
    down = resource_path(f'assets/down-{theme}.svg').as_posix()
    up = resource_path(f'assets/up-{theme}.svg').as_posix()
    check = resource_path(f'assets/check-{theme}.svg').as_posix()
    return f'''
    QWidget {{ color: {c['text']}; font-size: {base_points:.1f}pt; }}
    QMainWindow, QDialog, QWidget#shell, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['background']}; }}
    QLabel {{ background: transparent; }}
    QLabel[role="muted"], QLabel[role="kicker"] {{ color: {c['muted']}; }}
    QLabel[role="title"] {{ font-size: {base_points * 1.85:.1f}pt; font-weight: 650; }}
    QLabel[role="heading"] {{ font-size: {base_points * 1.3:.1f}pt; font-weight: 600; }}
    QLabel[role="kicker"] {{ font-weight: 600; }}
    QLabel[role="accent"] {{ color: {c['accent']}; font-weight: 600; }}
    QLabel[role="error"] {{ color: {c['error']}; }}
    QFrame#hero {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c['panel']},stop:1 {c['card']});
                   border: 1px solid {c['border']}; border-radius: 24px; }}
    QFrame#card, QFrame#footer {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 20px; }}
    QPushButton {{ background: {c['panel']}; color: {c['text']}; border: 2px solid {c['border']};
                  border-radius: 13px; padding: 9px 16px; min-height: 22px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton[primary="true"], QPushButton:checked {{ background: {c['accent']}; color: {c['on_accent']};
                                                       border-color: {c['accent']}; font-weight: 600; }}
    QPushButton:disabled {{ background: {c['panel']}; color: {c['muted']}; border-color: {c['border']}; }}
    QPushButton:focus {{ border: 3px dashed {c['focus']}; padding: 8px 15px; }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QListWidget, QTableWidget {{
        background: {c['field']}; color: {c['text']}; border: 2px solid {c['border']}; border-radius: 12px;
        padding: 8px; selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QListWidget:focus, QTableWidget:focus {{
        border: 3px solid {c['focus']}; padding: 7px; }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {c['muted']}; background: {c['panel']}; }}
    QComboBox {{ padding-right: 30px; }}
    QComboBox::drop-down {{ width: 24px; border: none; }}
    QComboBox::down-arrow {{ image: url("{down}"); width: 18px; height: 18px; }}
    QSpinBox {{ padding-right: 32px; }}
    QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 28px;
                         border-top-right-radius: 12px; background: {c['panel']}; }}
    QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 28px;
                           border-bottom-right-radius: 12px; background: {c['panel']}; }}
    QSpinBox::up-arrow {{ image: url("{up}"); width: 16px; height: 16px; }}
    QSpinBox::down-arrow {{ image: url("{down}"); width: 16px; height: 16px; }}
    QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']};
        selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; padding: 5px; }}
    QCheckBox {{ spacing: 10px; padding: 5px; border: 3px solid transparent; border-radius: 10px; }}
    QCheckBox:focus {{ border-color: {c['focus']}; }}
    QCheckBox::indicator {{ width: 22px; height: 22px; border: 2px solid {c['border']};
                           border-radius: 7px; background: {c['field']}; }}
    QCheckBox::indicator:checked {{ image: url("{check}"); background: {c['accent']}; border-color: {c['accent']}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: {c['panel']}; color: {c['text']}; border: 2px solid {c['border']};
                    border-radius: 17px; padding: 10px 20px; margin: 0 6px 10px 0; }}
    QTabBar::tab:selected {{ background: {c['accent']}; color: {c['on_accent']}; border-color: {c['accent']}; font-weight: 600; }}
    QTabBar::tab:focus {{ border: 3px solid {c['focus']}; padding: 9px 19px; }}
    QHeaderView::section {{ background: {c['panel']}; color: {c['text']}; border: none; padding: 10px; font-weight: 600; }}
    QTableWidget {{ gridline-color: transparent; }}
    QTableWidget::item, QListWidget::item {{ padding: 8px; border-radius: 6px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['accent']}; color: {c['on_accent']}; }}
    QTableWidget::item:focus, QListWidget::item:focus {{ border: 2px solid {c['focus']}; }}
    QScrollBar:vertical {{ background: {c['background']}; width: 16px; margin: 0; border-radius: 8px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 36px; border-radius: 8px; }}
    QScrollBar:horizontal {{ background: {c['background']}; height: 16px; margin: 0; border-radius: 8px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 36px; border-radius: 8px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QMenu {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
    QMenu::item {{ padding: 8px 20px; border-radius: 8px; }}
    QMenu::item:selected {{ background: {c['accent']}; color: {c['on_accent']}; }}
    QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 8px; }}
    '''


class FlowLayout(QLayout):
    """Wrap ordinary buttons at narrow widths and large text sizes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(10)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def arrange(self, rect, apply):
        x, y, line = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, line = rect.x(), y + line + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing()
            line = max(line, size.height())
        return y + line - rect.y()

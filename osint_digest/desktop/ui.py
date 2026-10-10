"""Accessible Qt desktop shell; collection and delivery remain in the isolated worker."""
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import (QAccessible, QAccessibleAnnouncementEvent, QFont, QIcon, QKeySequence,
                           QPalette, QShortcut, QTextCursor)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QTabWidget, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QCheckBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QListWidget, QListWidgetItem, QMessageBox, QFileDialog, QDialog,
    QDialogButtonBox, QSizePolicy)

from osint_digest.core.collector import error_label
from osint_digest.core.providers import PROVIDERS, KEY_ENV, PORTALS, list_models
from osint_digest.desktop.settings import (APP_NAME, VERSION, DEFAULTS, initialize, load_settings, save_settings,
                              atomic_json, resource_path)
from osint_digest.core.sources import make_source
from osint_digest.desktop.theme import (THEMES, FlowLayout, high_contrast_enabled, windows_palette,
                           palette_for, stylesheet)
from osint_digest.desktop.tray import Tray
from osint_digest.paths import PROJECT_ROOT

TITLES = {'feeds': 'Checking publisher feeds', 'ai': 'Testing AI on a real article',
          'preview': 'Previewing unsent articles', 'test': 'TEST MODE: sending limited articles; repeats allowed',
          'test-preview': 'TEST MODE: previewing limited articles; repeats allowed',
          'new': 'Checking for new articles', 'webhook': 'Checking Discord connection'}


def label(text, role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if role:
        widget.setProperty('role', role)
    return widget


def named(widget, name, description=''):
    widget.setAccessibleName(name)
    widget.setAccessibleDescription(description)
    widget.setToolTip(description or name)
    return widget


class DigestApp(QMainWindow):
    def __init__(self, root, discover_models=True, quit_on_exit=True):
        super().__init__()
        self.root = Path(root)
        initialize(self.root)
        self.quit_on_exit = quit_on_exit
        self.process = None
        self.monitoring = False
        self.next_check = 0
        self.quit_pending = False
        self.force_close = False
        self.alive = True
        self.tray = None
        self.buttons = []
        self.events = queue.Queue()
        self.model_choices = {}
        self.model_inflight = set()
        self.last_lookup = None
        self.settings_error = None
        try:
            self.settings = load_settings(self.root)
        except Exception:
            self.settings = deepcopy(DEFAULTS)
            self.settings_error = 'Saved settings could not be opened. Re-enter your connection details and save them.'
        self.profiles = deepcopy(self.settings['profiles'])
        self.active_provider = self.settings['provider']
        self.sources = json.loads((self.root / 'sources.json').read_text(encoding='utf-8'))
        self.qapp = QApplication.instance()
        self.system_palette = QPalette(self.qapp.palette())
        self.system_font = QFont(self.qapp.font())
        self.high_contrast = high_contrast_enabled()
        self.platform_colors = None
        self.last_platform_check = 0
        self._build()
        self.apply_appearance()
        self.rebuild_sources()
        self.refresh_reports()
        self.update_provider_fields()
        self.status_message(self.settings_error or ('Ready' if self.settings['webhook'] else 'Start with Connection to set up Discord and AI.'))
        if not self.settings['webhook'] or self.settings_error:
            self.tabs.setCurrentIndex(1)
        self.qapp.focusChanged.connect(self.ensure_focus_visible)
        self.qapp.installEventFilter(self)
        self.qapp.styleHints().colorSchemeChanged.connect(self.platform_theme_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(300)
        if discover_models:
            self.refresh_models(automatic=True)

    def _build(self):
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_path('assets/app.ico'))))
        self.setAccessibleName('OSINT Digest threat intelligence workspace')
        screen = self.screen().availableGeometry()
        self.resize(min(1160, screen.width() - 60), min(940, screen.height() - 60))
        self.setMinimumSize(620, 480)
        shell = QWidget()
        shell.setObjectName('shell')
        self.workspace_scroll = named(QScrollArea(), 'Workspace scroll area')
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll.setWidget(shell)
        self.setCentralWidget(self.workspace_scroll)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)
        hero = QFrame()
        hero.setObjectName('hero')
        top = QVBoxLayout(hero)
        top.setContentsMargins(24, 18, 24, 18)
        self.hero_kicker = label('OSINT / THREAT INTELLIGENCE', 'kicker')
        self.hero_title = label('Intelligence command center', 'title')
        self.hero_tagline = label('Collect. Analyze. Stay ahead.', 'muted')
        hero_row = QHBoxLayout()
        hero_text = QVBoxLayout()
        for text in (self.hero_kicker, self.hero_title, self.hero_tagline):
            hero_text.addWidget(text)
        hero_row.addLayout(hero_text, 1)
        self.radar = named(QLabel(), 'OSINT Digest radar illustration')
        self.radar.setPixmap(QIcon(str(resource_path('assets/radar.svg'))).pixmap(QSize(88, 88)))
        hero_row.addWidget(self.radar)
        top.addLayout(hero_row)
        preferences = QWidget()
        row = FlowLayout(preferences)
        self.theme_combo = named(QComboBox(), 'Appearance theme', 'Choose Dark, Light, or Windows. Windows contrast themes take priority.')
        for title, value in (('Dark', 'dark'), ('Light', 'light'), ('Windows', 'system')):
            self.theme_combo.addItem(title, value)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.settings['theme']))
        self.scale_combo = named(QComboBox(), 'Text size', 'Increase text size up to 200 percent. Ctrl+Plus and Ctrl+Minus also adjust text size.')
        for scale in (100, 125, 150, 175, 200):
            self.scale_combo.addItem(f'{scale}%', scale)
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(self.settings['text_scale']))
        for title, control in (('Theme', self.theme_combo), ('Text size', self.scale_combo)):
            group = QWidget()
            group_row = QHBoxLayout(group)
            group_row.setContentsMargins(0, 0, 0, 0)
            title_label = label(title)
            title_label.setBuddy(control)
            group_row.addWidget(title_label)
            group_row.addWidget(control)
            row.addWidget(group)
        row.addWidget(self.button('Keyboard help', self.keyboard_help, managed=False))
        top.addWidget(preferences)
        outer.addWidget(hero)
        self.tabs = named(QTabWidget(), 'Workspace sections', 'Use Ctrl+1 through Ctrl+4 to switch sections, or focus the tabs and use arrow keys.')
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setMinimumHeight(320)
        outer.addWidget(self.tabs, 1)
        self.pages = []
        for title in ('Dashboard', 'Connection', 'Sources', 'Previews'):
            scroll = named(QScrollArea(), title + ' scroll area')
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(2, 6, 12, 8)
            layout.setSpacing(16)
            scroll.setWidget(body)
            self.tabs.addTab(scroll, title)
            self.pages.append((scroll, layout))
        self._dashboard(self.pages[0][1])
        self._connection(self.pages[1][1])
        self._sources(self.pages[2][1])
        self._reports(self.pages[3][1])
        footer = QFrame()
        footer.setObjectName('footer')
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        self.status = named(label('Ready'), 'Application status')
        footer_layout.addWidget(self.status)
        controls = QWidget()
        buttons = FlowLayout(controls)
        self.busy = label('IDLE', 'accent')
        buttons.addWidget(self.busy)
        buttons.addWidget(self.button('Run in background', self.hide_to_tray, managed=False))
        buttons.addWidget(self.button('Exit', self.exit_app, managed=False))
        buttons.addWidget(label(f'v{VERSION}', 'muted'))
        footer_layout.addWidget(controls)
        outer.addWidget(footer)
        self.theme_combo.currentIndexChanged.connect(self.appearance_changed)
        self.scale_combo.currentIndexChanged.connect(self.appearance_changed)
        self.shortcuts = []
        for keys, action in [('Ctrl+S', self.save), ('F1', self.keyboard_help),
                             ('Ctrl++', lambda: self.adjust_scale(1)), ('Ctrl+=', lambda: self.adjust_scale(1)),
                             ('Ctrl+-', lambda: self.adjust_scale(-1)), ('Ctrl+0', lambda: self.scale_combo.setCurrentIndex(0))]:
            self.shortcut(keys, action)
        for i in range(4):
            self.shortcut(f'Ctrl+{i + 1}', lambda index=i: self.focus_page(index))

    def shortcut(self, keys, action):
        shortcut = QShortcut(QKeySequence(keys), self)
        shortcut.activated.connect(action)
        self.shortcuts.append(shortcut)

    def button(self, title, command, primary=False, managed=True):
        button = named(QPushButton(title), title)
        button.setProperty('primary', primary)
        button.setMinimumHeight(44)
        button.clicked.connect(lambda checked=False: command())
        if managed:
            self.buttons.append(button)
        return button

    def card(self, parent, title, subtitle=''):
        frame = named(QFrame(), title)
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(label(title, 'heading'))
        if subtitle:
            layout.addWidget(label(subtitle, 'muted'))
        if isinstance(parent, QGridLayout):
            parent.addWidget(frame, 0, parent.count())
        else:
            parent.addWidget(frame)
        return layout

    def actions(self, parent, actions):
        frame = QWidget()
        layout = FlowLayout(frame)
        buttons = []
        for title, command, primary in actions:
            button = self.button(title, command, primary)
            buttons.append(button)
            layout.addWidget(button)
        parent.addWidget(frame)
        return buttons

    def field(self, layout, title, widget, description=''):
        named(widget, title.replace('&', ''), description)
        text = label(title)
        text.setBuddy(widget)
        layout.addWidget(text)
        layout.addWidget(widget)
        return widget

    def _dashboard(self, page):
        pair = QWidget()
        self.dashboard_grid = QGridLayout(pair)
        self.dashboard_grid.setContentsMargins(0, 0, 0, 0)
        self.dashboard_grid.setSpacing(16)
        page.addWidget(pair)
        batch = self.card(self.dashboard_grid, 'Launch your intelligence digest', 'Check every enabled source and deliver all articles that have not been sent.')
        self.batch_card = batch.parentWidget()
        self.test_mode = named(QCheckBox('Test mode: allow repeats with an article limit'),
                               'Test mode: allow repeats with an article limit',
                               'Applies to manual Send and Preview only. Off each time the app opens.')
        batch.addWidget(self.test_mode)
        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 20)
        self.batch_size.setValue(self.settings['batch_size'])
        self.field(batch, 'Test article limit', self.batch_size, 'Maximum 1 to 20 articles in Test mode only.')
        self.selected_count = label('', 'accent')
        batch.addWidget(self.selected_count)
        self.send_button, self.preview_button, _ = self.actions(batch, [
            ('Check all and send new', lambda: self.start('test' if self.test_mode.isChecked() else 'new'), True),
            ('Preview unsent articles', lambda: self.start('test-preview' if self.test_mode.isChecked() else 'preview'), False),
            ('Test AI', lambda: self.start('ai'), False)])
        self.send_button.setAccessibleName('')
        self.preview_button.setAccessibleName('')
        self.test_status = label('', 'muted')
        batch.addWidget(self.test_status)
        self.test_mode.toggled.connect(self.update_test_mode)
        self.update_test_mode()
        auto = self.card(self.dashboard_grid, 'Continuous monitoring', 'Watch selected feeds for new research while your PC is awake.')
        self.auto_card = auto.parentWidget()
        self.interval = QSpinBox()
        self.interval.setRange(15, 360)
        self.interval.setSuffix(' minutes')
        self.interval.setValue(self.settings['interval_minutes'])
        self.field(auto, 'Check every', self.interval, 'Automatic check interval: 15 to 360 minutes.')
        self.actions(auto, [('Check and send new', lambda: self.start('new'), False)])
        self.auto_button = self.button('Start automatic checks', self.toggle_monitor, managed=False)
        # Let Qt derive the accessible name from the changing Start/Stop label.
        self.auto_button.setAccessibleName('')
        self.auto_button.setToolTip('Start or stop automatic feed checks.')
        auto.addWidget(self.auto_button)
        self.monitor_status = label('Automatic checks are off', 'accent')
        auto.addWidget(self.monitor_status)
        self.close_to_tray = named(QCheckBox('Keep running in the tray when I close the window'), 'Keep running in the tray when I close the window')
        self.close_to_tray.setChecked(self.settings['close_to_tray'])
        self.close_to_tray.toggled.connect(self.save_preferences)
        auto.addWidget(self.close_to_tray)
        auto.addWidget(label('Automatic checks always send unsent articles, even when manual Test mode is on. Use Exit to stop the app completely.', 'muted'))
        activity = self.card(page, 'Activity', 'Task progress and results. Pause updates to read at your own pace.')
        self.actions(activity, [('Check feeds', lambda: self.start('feeds'), False)])
        self.pause_log = named(QCheckBox('Pause live activity updates'), 'Pause live activity updates', 'Pause the display while reading. Collection and delivery continue.')
        activity.addWidget(self.pause_log)
        self.activity = self.text_area('Activity log', 'Read-only task output. Tab moves to the next control; Ctrl+A and Ctrl+C copy text.')
        activity.addWidget(self.activity)
        self.set_text(self.activity, 'Ready. Set up your connection and preview your first digest.')
        page.addStretch()

    def update_test_mode(self):
        testing = self.test_mode.isChecked()
        self.batch_size.setEnabled(testing)
        self.send_button.setText('Send test articles' if testing else 'Check all and send new')
        self.preview_button.setText('Preview test articles' if testing else 'Preview unsent articles')
        self.test_status.setText('TEST MODE: manual tasks can repeat sent articles, up to the test limit.' if testing else
                                'Normal mode: all enabled sources, all unsent articles, no article limit.')

    def _connection(self, page):
        form = self.card(page, 'Connect your workspace', 'Credentials are encrypted for your Windows account. Each provider keeps its own key and model.')
        self.webhook_entry = QLineEdit(self.settings['webhook'])
        self.webhook_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.field(form, 'Discord webhook URL', self.webhook_entry, 'Copy a webhook URL from Discord channel settings, Integrations, Webhooks.')
        self.provider = QComboBox()
        for title, value in PROVIDERS.items():
            self.provider.addItem(title, value)
        self.provider.setCurrentIndex(self.provider.findData(self.active_provider))
        self.field(form, 'Summary provider', self.provider)
        self.key_entry = QLineEdit(self.settings['api_key'])
        self.key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.field(form, 'AI API key', self.key_entry, 'API key for the selected provider. This value is hidden.')
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model_combo.setMinimumContentsLength(18)
        self.model_combo.setCurrentText(self.settings['model'])
        self.field(form, 'Model', self.model_combo, 'Choose a provider model or type its model ID. Alt+Down opens the list.')
        self.model_status = label('Refresh models to load choices for your provider.', 'muted')
        form.addWidget(self.model_status)
        self.model_refresh = self.button('Refresh models', self.refresh_models, managed=False)
        form.addWidget(self.model_refresh)
        self.show_keys = named(QCheckBox('Show credentials'), 'Show credentials', 'Reveal or hide both the Discord webhook and the selected API key.')
        self.show_keys.toggled.connect(self.reveal)
        form.addWidget(self.show_keys)
        self.actions(form, [('Save connection', self.save, True), ('Test Discord connection', lambda: self.start('webhook'), False),
                            ('Import from .env', self.import_env, False)])
        self.portal_button = self.button('Open provider portal', self.open_provider_portal, managed=False)
        form.addWidget(self.portal_button)
        form.addWidget(self.button('Open app data folder', lambda: os.startfile(str(self.root)), managed=False))
        form.addWidget(label('Cloud AI uses your account quota and billing. Publisher excerpts need no AI key; Ollama must run locally.', 'muted'))
        self.provider.currentIndexChanged.connect(self.provider_changed)
        self.key_entry.editingFinished.connect(lambda: self.refresh_models(automatic=True))
        page.addStretch()

    def _sources(self, page):
        body = self.card(page, 'Your intelligence sources', 'Every enabled source is checked on each run. Source order sets sampling priority in Test mode.')
        self.source_list = named(QTableWidget(0, 3), 'Publisher sources', 'Use arrow keys to select a row. Space toggles the selected source. Buttons below add, edit, remove, or reorder sources.')
        self.source_list.setHorizontalHeaderLabels(['Use', 'Publisher', 'Feed URL'])
        self.source_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.source_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_list.verticalHeader().hide()
        self.source_list.setShowGrid(False)
        self.source_list.setMinimumHeight(270)
        self.source_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.source_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.source_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.source_list.cellDoubleClicked.connect(lambda *_: self.toggle_source())
        toggle = QShortcut(QKeySequence(Qt.Key.Key_Space), self.source_list)
        toggle.setContext(Qt.ShortcutContext.WidgetShortcut)
        toggle.activated.connect(self.toggle_source)
        self.shortcuts_source = toggle
        body.addWidget(self.source_list)
        self.actions(body, [('Add source', self.source_editor, True), ('Edit source', lambda: self.source_editor(edit=True), False),
                            ('Enable / disable', self.toggle_source, False), ('Remove source', self.remove_source, False),
                            ('Move up', lambda: self.move_source(-1), False), ('Move down', lambda: self.move_source(1), False),
                            ('Save sources', self.save, False)])
        body.addWidget(label('Public HTTPS RSS or Atom feeds are supported. Disabling a source keeps its delivery history.', 'muted'))
        page.addStretch()

    def _reports(self, page):
        body = self.card(page, 'Review before delivery', 'Previews stay on this PC. Creating a preview does not send a Discord message.')
        self.actions(body, [('Refresh previews', self.refresh_reports, False)])
        self.report_list = named(QListWidget(), 'Article previews', 'Use arrow keys to select an article. Its full preview appears in the next text area.')
        self.report_list.setMinimumHeight(160)
        self.report_list.currentRowChanged.connect(self.show_report)
        body.addWidget(self.report_list)
        self.report_text = self.text_area('Selected article preview', 'Read-only article analysis. Links and extracted identifiers are available as text.')
        self.report_text.setMinimumHeight(300)
        body.addWidget(self.report_text)
        self.set_text(self.report_text, 'Use Test AI or Preview to create a preview.')
        page.addStretch()

    def text_area(self, name, description):
        widget = named(QPlainTextEdit(), name, description)
        widget.setReadOnly(True)
        widget.setTabChangesFocus(True)
        widget.setMinimumHeight(180)
        return widget

    @staticmethod
    def set_text(widget, text):
        if widget.toPlainText() == text:
            return
        scroll = widget.verticalScrollBar()
        at_end, position = scroll.value() >= scroll.maximum() - 2, scroll.value()
        old = widget.toPlainText()
        if old and text.startswith(old):
            cursor = QTextCursor(widget.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text[len(old):])
        else:
            widget.setPlainText(text)
        scroll.setValue(scroll.maximum() if at_end else position)

    def status_message(self, text):
        if self.status.text() == text:
            return
        self.status.setText(text)
        if QAccessible.isActive():
            QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.status, text))

    def focus_page(self, index):
        self.tabs.setCurrentIndex(index)
        self.tabs.tabBar().setFocus()

    def ensure_focus_visible(self, old, current):
        if current and (current.window() is self or current.window().parent() is self):
            ancestor = current.parentWidget()
            while ancestor:
                if isinstance(ancestor, QScrollArea):
                    ancestor.ensureWidgetVisible(current, 18, 24)
                ancestor = ancestor.parentWidget()

    def eventFilter(self, watched, event):
        # Windows theme/font changes are observed; system settings are never changed.
        if event.type() == QEvent.Type.ApplicationFontChange and not getattr(self, '_applying_theme', False):
            self.system_font = QFont(self.qapp.font())
            self.apply_appearance()
        return super().eventFilter(watched, event)

    def apply_appearance(self):
        self._applying_theme = True
        try:
            self.high_contrast = high_contrast_enabled()
            system = windows_palette(self.system_palette)
            self.platform_colors = tuple(system.color(role).rgba() for role in (
                QPalette.ColorRole.Window, QPalette.ColorRole.WindowText, QPalette.ColorRole.Highlight))
            mode = self.theme_combo.currentData()
            scale = self.scale_combo.currentData() / 100
            font = QFont(self.system_font)
            points = max(1, font.pointSizeF())
            if mode != 'system' and not self.high_contrast:
                points = max(11, points)
            font.setPointSizeF(points * scale)
            self.setFont(font)
            if self.high_contrast or mode == 'system':
                self.qapp.setStyleSheet('')
                self.qapp.setPalette(system if self.high_contrast else self.system_palette)
            else:
                self.qapp.setPalette(palette_for(THEMES[mode]))
                self.qapp.setStyleSheet(stylesheet(mode, points * scale))
            self.source_list.verticalHeader().setDefaultSectionSize(max(44, int(points * scale * 3.5)))
            self.update_compact_header()
        finally:
            self._applying_theme = False

    def update_compact_header(self):
        compact = self.width() < 900 or self.scale_combo.currentData() >= 150
        self.hero_kicker.setVisible(not compact)
        self.hero_tagline.setVisible(not compact)
        self.radar.setVisible(not compact)
        self.hero_title.setText('OSINT Digest' if compact else 'Intelligence command center')
        self.hero_title.setProperty('role', 'heading' if compact else 'title')
        self.hero_title.style().unpolish(self.hero_title)
        self.hero_title.style().polish(self.hero_title)
        if hasattr(self, 'auto_card'):
            wide = self.width() >= 1050 and self.scale_combo.currentData() == 100
            self.dashboard_grid.removeWidget(self.batch_card)
            self.dashboard_grid.removeWidget(self.auto_card)
            self.dashboard_grid.addWidget(self.batch_card, 0, 0)
            self.dashboard_grid.addWidget(self.auto_card, 0 if wide else 1, 1 if wide else 0)
            self.dashboard_grid.setColumnStretch(0, 1)
            self.dashboard_grid.setColumnStretch(1, 1 if wide else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scale_combo'):
            self.update_compact_header()

    def appearance_changed(self):
        self.apply_appearance()
        self.save_preferences()

    def platform_theme_changed(self):
        self.system_palette = QPalette(self.qapp.style().standardPalette())
        self.apply_appearance()

    def adjust_scale(self, offset):
        self.scale_combo.setCurrentIndex(max(0, min(self.scale_combo.count() - 1, self.scale_combo.currentIndex() + offset)))

    def save_preferences(self):
        try:
            saved = load_settings(self.root)
            for key, value in (('theme', self.theme_combo.currentData()), ('text_scale', self.scale_combo.currentData()),
                               ('close_to_tray', self.close_to_tray.isChecked())):
                saved[key] = self.settings[key] = value
            save_settings(self.root, saved)
            self.status_message('Appearance and background preferences saved.')
        except Exception:
            self.status_message('Preference changed for this session. Unable to save it to the app data folder.')

    def keyboard_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Keyboard and accessibility')
        dialog.resize(min(740, self.screen().availableGeometry().width() - 80), 560)
        layout = QVBoxLayout(dialog)
        help_text = self.text_area('Keyboard and accessibility help', 'Scrollable help. Tab moves to the Close button; Escape closes this dialog.')
        help_text.setPlainText(
            'Tab / Shift+Tab: move between controls. Focus stays visible when pages scroll.\n'
            'Space: activate buttons and checkboxes; enable or disable a selected source.\n'
            'Arrow keys: navigate tabs, models, source rows, and previews.\n'
            'Ctrl+1 to Ctrl+4: Dashboard, Connection, Sources, Previews.\n'
            'Ctrl+S: save connection and source changes.\n'
            'Ctrl+Plus / Ctrl+Minus: resize text. Ctrl+0: reset to 100%.\n'
            'F1: open this help. Escape: cancel a dialog.\n\n'
            'Dark and Light themes use high-contrast text and focus outlines. Windows theme uses platform colors and fonts. '
            'Windows contrast themes take priority. Text size supports 100–200%.\n'
            'Pause live activity updates to read without new output appearing. Tasks keep running. '
            'Every action has a keyboard control; status also appears as text.')
        layout.addWidget(help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        help_text.setFocus()
        dialog.exec()

    def reveal(self):
        mode = QLineEdit.EchoMode.Normal if self.show_keys.isChecked() else QLineEdit.EchoMode.Password
        self.webhook_entry.setEchoMode(mode)
        self.key_entry.setEchoMode(mode)

    def remember_provider(self):
        self.profiles[self.active_provider] = {'api_key': self.key_entry.text().strip(), 'model': self.model_combo.currentText().strip()}

    def provider_changed(self):
        self.remember_provider()
        self.active_provider = self.provider.currentData()
        profile = self.profiles.get(self.active_provider, {})
        self.key_entry.setText(profile.get('api_key', ''))
        self.model_combo.clear()
        self.model_combo.addItems(self.model_choices.get(self.active_provider, []))
        self.model_combo.setCurrentText(profile.get('model', ''))
        self.show_keys.setChecked(False)
        self.reveal()
        self.last_lookup = None
        self.update_provider_fields()
        self.refresh_models(automatic=True)

    def update_provider_fields(self):
        self.key_entry.setEnabled(self.active_provider in KEY_ENV)
        self.model_combo.setEnabled(self.active_provider != 'none')
        self.model_refresh.setEnabled(self.active_provider != 'none')
        self.portal_button.setEnabled(self.active_provider in PORTALS)
        self.model_status.setText('No AI key or model needed.' if self.active_provider == 'none' else
                                  'Refresh to list installed models. Ollama must be running.' if self.active_provider == 'ollama' else
                                  'Enter this provider\'s key, then refresh models. You can also type a model ID.')

    def open_provider_portal(self):
        if self.active_provider in PORTALS:
            webbrowser.open(PORTALS[self.active_provider])

    def refresh_models(self, automatic=False):
        provider, key = self.active_provider, self.key_entry.text().strip()
        identity = (provider, key)
        if provider == 'none' or (provider in KEY_ENV and not key):
            return
        if identity in self.model_inflight or (automatic and identity == self.last_lookup):
            return
        self.last_lookup = identity
        self.model_inflight.add(identity)
        self.model_status.setText('Loading models from your provider…')
        def work():
            try:
                models, error = list_models(provider, key), None
            except Exception as exc:
                models, error = [], error_label(exc)
            self.events.put((identity, models, error))
        threading.Thread(target=work, daemon=True).start()

    def handle_events(self):
        while not self.events.empty():
            identity, models, error = self.events.get_nowait()
            self.model_inflight.discard(identity)
            if identity != (self.active_provider, self.key_entry.text().strip()):
                continue
            if error:
                self.model_status.setText(f'Could not load models ({error}). Check your key and connection, then refresh.')
            else:
                current = self.model_combo.currentText()
                self.model_choices[self.active_provider] = models
                self.model_combo.clear()
                self.model_combo.addItems(models)
                self.model_combo.setCurrentText(current)
                self.model_status.setText(f'{len(models)} models loaded. Choose a text model and use Test AI.' if models else
                                          'No text models found. Check access or enter a model ID.')

    def rebuild_sources(self, selected=None):
        self.source_list.setRowCount(len(self.sources))
        for row, source in enumerate(self.sources):
            for column, value in enumerate(('Enabled' if source.get('enabled', True) else 'Disabled', source['name'], source['feed'])):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.source_list.setItem(row, column, item)
        if selected is not None and self.sources:
            self.source_list.selectRow(selected)
        self.selected_count.setText(f'{sum(s.get("enabled", True) for s in self.sources)} sources enabled')

    def selected_source(self):
        row = self.source_list.currentRow()
        return row if row >= 0 else None

    def toggle_source(self):
        index = self.selected_source()
        if self.process or index is None:
            return
        self.sources[index]['enabled'] = not self.sources[index].get('enabled', True)
        self.rebuild_sources(index)
        self.status_message('Source selection changed. Save sources to apply.')

    def move_source(self, offset):
        index = self.selected_source()
        if self.process or index is None or not 0 <= index + offset < len(self.sources):
            return
        self.sources[index], self.sources[index + offset] = self.sources[index + offset], self.sources[index]
        self.rebuild_sources(index + offset)
        self.status_message('Source order changed. Save sources to apply.')

    def remove_source(self):
        index = self.selected_source()
        if self.process or index is None:
            return
        self.sources.pop(index)
        self.rebuild_sources(min(index, len(self.sources) - 1) if self.sources else None)
        self.status_message('Source removed from this list. Save sources to apply. Delivery history is retained.')

    def source_editor(self, edit=False):
        index = self.selected_source() if edit else None
        if self.process or (edit and index is None):
            return
        source = self.sources[index] if edit else {'name': '', 'feed': '', 'hosts': [], 'enabled': True}
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit source' if edit else 'Add RSS / Atom source')
        dialog.resize(min(700, self.screen().availableGeometry().width() - 80), 520)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        fields_layout = QVBoxLayout(body)
        fields = {}
        for name, title, value in (('name', 'Publisher name', source['name']), ('feed', 'HTTPS feed URL', source['feed']),
                                   ('hosts', 'Article and redirect hosts', ', '.join(source['hosts']))):
            fields[name] = QLineEdit(value)
            self.field(fields_layout, title, fields[name])
        fields['name'].setReadOnly(edit)
        fields_layout.addWidget(label('Enter an RSS or Atom URL. The feed host is included automatically. Add exact article or redirect domains separated by commas, such as example.com, www.example.com.', 'muted'))
        error_label_widget = named(label('', 'error'), 'Source validation error')
        fields_layout.addWidget(error_label_widget)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        outer.addWidget(controls)
        controls.rejected.connect(dialog.reject)
        def accept():
            try:
                value = make_source(*(fields[k].text() for k in ('name', 'feed', 'hosts')),
                                    self.sources, editing=index, enabled=source.get('enabled', True))
            except ValueError as exc:
                error_label_widget.setText(str(exc))
                fields['feed'].setFocus()
                if QAccessible.isActive():
                    QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(error_label_widget, str(exc)))
                return
            if edit:
                self.sources[index] = value
            else:
                self.sources.append(value)
            self.rebuild_sources(index if edit else len(self.sources) - 1)
            self.status_message('Source updated. Save sources, then use Check feeds on the Dashboard.')
            dialog.accept()
        controls.accepted.connect(accept)
        fields['feed' if edit else 'name'].setFocus()
        dialog.exec()

    def save(self):
        if self.process:
            self.status_message('Wait for the current task before saving connection or source changes.')
            return False
        try:
            self.remember_provider()
            value = {**self.settings, 'provider': self.active_provider, 'api_key': self.key_entry.text().strip(),
                     'model': self.model_combo.currentText().strip(), 'webhook': self.webhook_entry.text().strip(),
                     'profiles': deepcopy(self.profiles), 'batch_size': self.batch_size.value(),
                     'interval_minutes': self.interval.value(), 'close_to_tray': self.close_to_tray.isChecked(),
                     'theme': self.theme_combo.currentData(), 'text_scale': self.scale_combo.currentData()}
            if not any(s.get('enabled', True) for s in self.sources):
                self.focus_page(2)
                raise ValueError('Enable at least one source.')
            save_settings(self.root, value)
            atomic_json(self.root / 'sources.json', self.sources)
            if self.monitoring and value['interval_minutes'] != self.settings['interval_minutes']:
                self.next_check = time.time() + value['interval_minutes'] * 60
            self.settings = value
            self.status_message('Connection and sources saved.')
            return True
        except ValueError as exc:
            self.status_message('Check settings: ' + str(exc))
            QMessageBox.warning(self, 'Check settings', str(exc))
        except Exception:
            self.status_message('Unable to save. Check access to the app data folder.')
        return False

    def import_env(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose your existing .env file', '', 'Environment files (.env);;All files (*)')
        if not path:
            return
        try:
            values = {}
            for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
            provider = values.get('AI_PROVIDER', 'gemini').lower()
            if provider not in PROVIDERS.values():
                raise ValueError()
            self.remember_provider()
            for item, env in KEY_ENV.items():
                if values.get(env):
                    self.profiles.setdefault(item, {'model': '', 'api_key': ''})['api_key'] = values[env]
            self.provider.blockSignals(True)
            self.provider.setCurrentIndex(self.provider.findData(provider))
            self.provider.blockSignals(False)
            self.active_provider = provider
            profile = self.profiles.get(provider, {})
            self.key_entry.setText(profile.get('api_key', ''))
            self.model_combo.clear()
            self.model_combo.setCurrentText(values.get('AI_MODEL', profile.get('model', '')))
            if values.get('DISCORD_WEBHOOK_URL'):
                self.webhook_entry.setText(values['DISCORD_WEBHOOK_URL'])
            self.last_lookup = None
            self.update_provider_fields()
            self.refresh_models(automatic=True)
            self.status_message('Connection imported. Save connection to store it.')
        except Exception:
            self.provider.blockSignals(False)
            self.status_message('Unable to read that connection file or provider.')

    def start(self, action):
        if action in ('test', 'test-preview') and not self.test_mode.isChecked():
            self.status_message('Enable Test mode to allow repeated and limited articles.')
            return False
        if self.process or self.quit_pending or not self.save():
            return False
        value = self.settings
        error, field = None, self.webhook_entry
        if action in ('test', 'new', 'webhook') and not value['webhook']:
            error = 'Add your Discord webhook URL first.'
        elif action not in ('feeds', 'webhook') and value['provider'] in KEY_ENV and not value['api_key']:
            error, field = 'Add the selected provider\'s AI API key first.', self.key_entry
        elif action == 'ai' and value['provider'] == 'none':
            error, field = 'Choose an AI provider to test a summary.', self.provider
        elif action not in ('feeds', 'webhook') and value['provider'] != 'none' and not value['model']:
            error, field = 'Choose a model or enter its model ID.', self.model_combo
        if error:
            self.tabs.setCurrentIndex(1)
            field.setFocus()
            self.status_message(error)
            return False
        if action != 'webhook' and not any(s.get('enabled', True) for s in self.sources):
            self.status_message('Enable at least one publisher in Sources.')
            self.tabs.setCurrentIndex(2)
            return False
        try:
            (self.root / 'activity.log').write_text('', encoding='utf-8')
            command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(PROJECT_ROOT / 'desktop.py')]
            command += ['--data-dir', str(self.root), '--worker', action]
            self.process = subprocess.Popen(command, cwd=str(self.root), env=os.environ.copy(),
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.current_action = action
            self.last_log = ''
            if not self.pause_log.isChecked():
                self.set_text(self.activity, TITLES[action] + '…')
            self.status_message(TITLES[action] + '…')
            self.busy.setText('TASK RUNNING')
            for button in self.buttons:
                button.setEnabled(False)
            return True
        except Exception:
            self.process = None
            self.status_message('Unable to start the task. Check access to the app folder.')
            return False

    def stop_checks(self):
        self.monitoring = False
        self.auto_button.setText('Start automatic checks')
        self.monitor_status.setText('Automatic checks are off. Any current task will finish.')

    def toggle_monitor(self):
        if self.monitoring:
            self.stop_checks()
        elif not self.process and self.start('new'):
            self.monitoring = True
            self.next_check = time.time() + self.settings['interval_minutes'] * 60
            self.auto_button.setText('Stop automatic checks')

    def read_log(self):
        if self.pause_log.isChecked():
            return
        try:
            text = (self.root / 'activity.log').read_text(encoding='utf-8', errors='replace')[-150000:]
            if text != self.last_log:
                self.set_text(self.activity, text)
                self.last_log = text
        except OSError:
            pass

    def poll(self):
        if not self.alive:
            return
        if time.monotonic() - self.last_platform_check > 2:
            self.last_platform_check = time.monotonic()
            platform = windows_palette(self.system_palette)
            colors = tuple(platform.color(role).rgba() for role in (
                QPalette.ColorRole.Window, QPalette.ColorRole.WindowText, QPalette.ColorRole.Highlight))
            if high_contrast_enabled() != self.high_contrast or colors != self.platform_colors:
                self.apply_appearance()
        try:
            request = self.root / '.show-window'
            if request.exists():
                request.unlink()
                self.restore_window()
        except OSError:
            pass
        self.handle_events()
        if self.process:
            self.read_log()
            code = self.process.poll()
            if code is not None:
                self.read_log()
                self.process = None
                self.busy.setText('IDLE')
                for button in self.buttons:
                    button.setEnabled(True)
                self.status_message('Task finished successfully.' if code == 0 else 'Task finished with errors. Read Activity for details.')
                self.refresh_reports()
                if self.monitoring:
                    self.next_check = time.time() + self.settings['interval_minutes'] * 60
        elif hasattr(self, 'last_log'):
            self.read_log()
        if self.quit_pending and not self.process:
            self.exit_app()
            return
        if self.monitoring:
            self.monitor_status.setText('Automatic checks on. Next check: ' + time.strftime('%I:%M %p', time.localtime(self.next_check)))
            if not self.process and time.time() >= self.next_check and not self.start('new'):
                self.stop_checks()

    def refresh_reports(self):
        selected = self.report_list.currentItem()
        previous = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.report_list.blockSignals(True)
        self.report_list.clear()
        paths = sorted((self.root / 'preview').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        selection = 0
        for path in paths:
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                item = QListWidgetItem(f'{report["source"]} — {report["title"]}')
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.report_list.addItem(item)
                if str(path) == previous:
                    selection = self.report_list.count() - 1
            except (OSError, ValueError, KeyError):
                continue
        self.report_list.blockSignals(False)
        if self.report_list.count():
            self.report_list.setCurrentRow(selection)

    def show_report(self, row=None):
        selected = self.report_list.currentItem()
        if not selected:
            return
        try:
            report = json.loads(Path(selected.data(Qt.ItemDataRole.UserRole)).read_text(encoding='utf-8'))
            lines = [report['title'], report['url'], '', report['ai_status'], '']
            if report.get('analysis'):
                for key, title in (('summary', 'SUMMARY'), ('affected', 'AFFECTED'), ('actors', 'ACTORS / MALWARE'),
                                   ('techniques', 'TECHNIQUES'), ('actions', 'RECOMMENDATIONS')):
                    lines += [title] + [claim['text'] for claim in report['analysis'].get(key, [])] + ['']
            else:
                lines += ['PUBLISHER EXCERPT', report.get('publisher_excerpt', ''), '']
            lines += ['CVEs: ' + (', '.join(report.get('cves', [])) or 'None mentioned'),
                      'ATT&CK: ' + (', '.join(report.get('attack_ids', [])) or 'None mentioned'),
                      f'IOC candidates: {len(report.get("iocs", []))}']
            self.set_text(self.report_text, '\n'.join(lines))
        except (OSError, ValueError, KeyError):
            self.set_text(self.report_text, 'This preview could not be opened. Generate a new preview to replace it.')

    def hide_to_tray(self):
        if not self.tray:
            self.tray = Tray(self, resource_path('assets/app.ico'), self.restore_window, self.stop_checks, self.exit_app)
        if self.tray.start():
            self.status_message('Running in the system tray. Open OSINT Digest from the icon near the clock.')
            self.hide()
        else:
            self.status_message('System tray unavailable. Minimized to the taskbar; existing checks continue.')
            self.showMinimized()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.force_close:
            event.accept()
        else:
            event.ignore()
            if self.close_to_tray.isChecked():
                self.hide_to_tray()
            else:
                self.exit_app()

    def exit_app(self):
        self.stop_checks()
        self.quit_pending = True
        if self.process:
            self.auto_button.setEnabled(False)
            self.status_message('Exiting after the current task finishes…')
            return
        self.alive = False
        self.timer.stop()
        if self.tray:
            self.tray.stop()
        self.force_close = True
        self.qapp.removeEventFilter(self)
        self.qapp.focusChanged.disconnect(self.ensure_focus_visible)
        self.qapp.styleHints().colorSchemeChanged.disconnect(self.platform_theme_changed)
        self.close()
        if self.quit_on_exit:
            self.qapp.quit()

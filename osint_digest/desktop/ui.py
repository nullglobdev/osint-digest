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
    QSpinBox, QCheckBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout,
    QAbstractItemView, QMessageBox, QFileDialog, QDialog,
    QDialogButtonBox, QSizePolicy)

from osint_digest.core.collector import error_label
from osint_digest.core.providers import PROVIDERS, KEY_ENV, PORTALS, list_models
from osint_digest.desktop.settings import (APP_NAME, VERSION, DEFAULTS, initialize, load_settings, save_settings,
                              atomic_json, resource_path)
from osint_digest.core.sources import make_source
from osint_digest.core import scopes
from osint_digest.desktop.theme import (THEMES, FlowLayout, high_contrast_enabled, windows_palette,
                           palette_for, stylesheet)
from osint_digest.desktop.tray import Tray
from osint_digest.desktop.reports import ReportPanel
from osint_digest.paths import PROJECT_ROOT

TITLES = {'feeds': 'Checking publisher feeds', 'ai': 'Testing AI on a real article',
          'preview': 'Previewing unsent articles', 'test': 'TEST MODE: collecting limited articles; repeats allowed',
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
        self.last_results_check = 0
        self.status_message(self.settings_error or 'Ready. Collect new articles or start automatic checks.')
        if self.settings_error:
            self.tabs.setCurrentIndex(1)
        self.focus_scroll_timer = QTimer(self)
        self.focus_scroll_timer.setSingleShot(True)
        self.focus_scroll_timer.timeout.connect(self.scroll_to_focus)
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
        self.resize(min(1040, screen.width() - 60), min(740, screen.height() - 60))
        self.setMinimumSize(620, 480)
        shell = QWidget()
        shell.setObjectName('shell')
        self.workspace_scroll = named(QScrollArea(), 'Workspace scroll area')
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll.setWidget(shell)
        self.setCentralWidget(self.workspace_scroll)
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)
        hero = QFrame()
        hero.setObjectName('hero')
        top = QHBoxLayout(hero)
        top.setContentsMargins(12, 8, 12, 8)
        self.radar = named(QLabel(), 'OSINT Digest radar illustration')
        self.radar.setPixmap(QIcon(str(resource_path('assets/radar.svg'))).pixmap(QSize(32, 32)))
        top.addWidget(self.radar)
        self.hero_title = label('OSINT Digest', 'heading')
        top.addWidget(self.hero_title)
        top.addStretch()
        self.destination = label('', 'accent')
        top.addWidget(self.destination)
        outer.addWidget(hero)
        self.tabs = named(QTabWidget(), 'Workspace sections', 'Use Ctrl+1 through Ctrl+5 to switch sections. Ctrl+6 opens Previews in Dev mode. Ctrl+7 focuses article filters on the Dashboard.')
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setMinimumHeight(320)
        outer.addWidget(self.tabs, 1)
        self.pages = []
        for title in ('Dashboard', 'Connection', 'Sources', 'Results', 'Preferences', 'Previews'):
            scroll = named(QScrollArea(), title + ' scroll area')
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(0, 2, 6, 2)
            layout.setSpacing(10)
            scroll.setWidget(body)
            self.tabs.addTab(scroll, title)
            self.pages.append((scroll, layout))
        self._preferences(self.pages[4][1])
        self._dashboard(self.pages[0][1])
        self._connection(self.pages[1][1])
        self._sources(self.pages[2][1])
        self.results_panel = ReportPanel(self.root / 'results')
        self.pages[3][1].addWidget(self.results_panel, 1)
        self._reports(self.pages[5][1])
        footer = QFrame()
        footer.setObjectName('footer')
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        self.status = named(label('Ready'), 'Application status')
        footer_layout.addWidget(self.status, 1)
        controls = QWidget()
        buttons = FlowLayout(controls)
        self.busy = label('IDLE', 'accent')
        buttons.addWidget(self.busy)
        buttons.addWidget(self.button('Run in background', self.hide_to_tray, managed=False))
        buttons.addWidget(self.button('Exit', self.exit_app, managed=False))
        buttons.addWidget(label(f'v{VERSION}', 'muted'))
        footer_layout.addWidget(controls, 1)
        outer.addWidget(footer)
        self.theme_combo.currentIndexChanged.connect(self.appearance_changed)
        self.scale_combo.currentIndexChanged.connect(self.appearance_changed)
        self.close_to_tray.toggled.connect(self.save_preferences)
        self.pause_log.toggled.connect(self.save_preferences)
        self.per_source_limit.valueChanged.connect(self.save_preferences)
        self.per_source_limit.valueChanged.connect(self.update_test_mode)
        for combo in self.scope_controls.values():
            combo.currentIndexChanged.connect(self.scope_changed)
        self.apply_scope()
        self.developer_mode.toggled.connect(self.developer_mode_changed)
        self.test_mode.toggled.connect(self.update_test_mode)
        self.test_lookback_days.valueChanged.connect(self.save_preferences)
        self.test_lookback_days.valueChanged.connect(self.update_test_mode)
        self.update_developer_mode()
        self.shortcuts = []
        for keys, action in [('Ctrl+S', self.save), ('F1', self.keyboard_help),
                             ('Ctrl++', lambda: self.adjust_scale(1)), ('Ctrl+=', lambda: self.adjust_scale(1)),
                             ('Ctrl+-', lambda: self.adjust_scale(-1)), ('Ctrl+0', lambda: self.scale_combo.setCurrentIndex(0))]:
            self.shortcut(keys, action)
        for i in range(len(self.pages)):
            self.shortcut(f'Ctrl+{i + 1}', lambda index=i: self.focus_page(index))
        self.shortcut('Ctrl+7', self.focus_filters)

    def shortcut(self, keys, action):
        shortcut = QShortcut(QKeySequence(keys), self)
        shortcut.activated.connect(action)
        self.shortcuts.append(shortcut)

    def button(self, title, command, primary=False, managed=True):
        button = named(QPushButton(title), title)
        button.setProperty('primary', primary)
        button.setMinimumHeight(30)
        button.clicked.connect(lambda checked=False: command())
        if managed:
            self.buttons.append(button)
        return button

    def card(self, parent, title, subtitle=''):
        frame = named(QFrame(), title)
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
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
        self.dashboard_grid.setSpacing(10)
        page.addWidget(pair)
        batch = self.card(self.dashboard_grid, 'Collect articles')
        self.collection_description = label('', 'muted')
        batch.addWidget(self.collection_description)
        self.batch_card = batch.parentWidget()
        self.selected_count = label('', 'accent')
        batch.addWidget(self.selected_count)
        self.per_source_limit = QSpinBox()
        self.per_source_limit.setRange(1, 100)
        self.per_source_limit.setValue(self.settings['per_source_limit'])
        self.field(batch, 'Articles per source', self.per_source_limit,
                   'Maximum articles per source per check, from 1 to 100. Applies to manual and automatic checks, previews, and Dev mode resends.')
        self.send_button, self.preview_button, self.ai_test_button = self.actions(batch, [
            ('Collect new', lambda: self.start('test' if self.test_mode.isChecked() else 'new'), True),
            ('Preview', lambda: self.start('test-preview' if self.test_mode.isChecked() else 'preview'), False),
            ('Test AI', lambda: self.start('ai'), False)])
        self.send_button.setAccessibleName('')
        self.preview_button.setAccessibleName('')
        self.test_status = label('', 'muted')
        batch.addWidget(self.test_status)
        self.update_test_mode()
        auto = self.card(self.dashboard_grid, 'Automatic checks')
        self.auto_card = auto.parentWidget()
        self.interval = QSpinBox()
        self.interval.setRange(15, 360)
        self.interval.setSuffix(' minutes')
        self.interval.setValue(self.settings['interval_minutes'])
        self.field(auto, 'Check every', self.interval, 'Automatic check interval: 15 to 360 minutes.')
        self.auto_button = self.button('Start automatic checks', self.toggle_monitor, managed=False)
        # Let Qt derive the accessible name from the changing Start/Stop label.
        self.auto_button.setAccessibleName('')
        self.auto_button.setToolTip('Start or stop automatic feed checks.')
        auto.addWidget(self.auto_button)
        self.monitor_status = label('Automatic checks are off', 'accent')
        auto.addWidget(self.monitor_status)
        auto.addWidget(label('Always checks for new articles. The PC must be awake and online.', 'muted'))
        self._filters(self.dashboard_grid)
        activity = self.card(page, 'Activity')
        self.actions(activity, [('Check feeds', lambda: self.start('feeds'), False)])
        self.activity = self.text_area('Activity log', 'Read-only task output. Tab moves to the next control; Ctrl+A and Ctrl+C copy text.')
        activity.addWidget(self.activity)
        self.set_text(self.activity, 'Ready. Leave the webhook blank to publish in Results, or add one in Connection to send to Discord.')
        page.setStretch(1, 1)

    def _filters(self, page):
        card = self.card(page, 'Article filters', 'Every selected scope must match. All leaves a scope unrestricted.')
        self.filters_card = card.parentWidget()
        self.filter_summary = label('', 'muted')
        card.addWidget(self.filter_summary)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(7)
        self.scope_controls = {}
        for key, choices in scopes.CHOICES.items():
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(22)
            named(combo, 'Sector scope' if key == 'sector_scope' else scopes.LABELS[key],
                  'Choose one option, or All for no restriction. Selection saves immediately and also filters Results and Previews.')
            for value, title in choices.items():
                combo.addItem(title, value)
            combo.setCurrentIndex(combo.findData(self.settings[key]))
            title = label(scopes.LABELS[key].replace('&', '&&'))
            title.setBuddy(combo)
            form.addRow(title, combo)
            self.scope_controls[key] = combo
        self.sector_scope = self.scope_controls['sector_scope']
        card.addLayout(form)
        self.actions(card, [('View selected keywords', self.show_scope_keywords, False),
                            ('Reset all filters', self.reset_filters, False)])

    def focus_filters(self):
        self.focus_page(0)
        self.sector_scope.setFocus()

    def _preferences(self, page):
        appearance = self.card(page, 'Appearance and accessibility')
        self.theme_combo = named(QComboBox(), 'Appearance theme', 'Dark, Light, or Windows. Windows contrast themes take priority.')
        for title, value in (('Dark', 'dark'), ('Light', 'light'), ('Windows', 'system')):
            self.theme_combo.addItem(title, value)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.settings['theme']))
        self.scale_combo = named(QComboBox(), 'Text size', 'Increase text size up to 200 percent. Ctrl+Plus and Ctrl+Minus also adjust text size.')
        for scale in (100, 125, 150, 175, 200):
            self.scale_combo.addItem(f'{scale}%', scale)
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(self.settings['text_scale']))
        fields = QWidget()
        row = FlowLayout(fields)
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
        appearance.addWidget(fields)
        self.pause_log = named(QCheckBox('Pause live activity updates'), 'Pause live activity updates', 'Pause the Activity log display while reading. Collection and delivery continue.')
        self.pause_log.setChecked(self.settings['pause_log'])
        appearance.addWidget(self.pause_log)
        behavior = self.card(page, 'Background behavior')
        self.close_to_tray = named(QCheckBox('Keep running in the tray when I close the window'), 'Keep running in the tray when I close the window')
        self.close_to_tray.setChecked(self.settings['close_to_tray'])
        behavior.addWidget(self.close_to_tray)
        behavior.addWidget(label('Exit stops future checks and lets any active task finish.', 'muted'))
        developer = self.card(page, 'Developer tools')
        self.developer_mode = named(QCheckBox('Enable Dev mode'), 'Enable Dev mode', 'Show preview tools and AI tests. Previews use AI quota but do not publish articles.')
        self.developer_mode.setChecked(self.settings['developer_mode'])
        developer.addWidget(self.developer_mode)
        developer.addWidget(label('Previews and AI tests are available only in Dev mode.', 'muted'))
        self.test_controls = QWidget()
        test_layout = QVBoxLayout(self.test_controls)
        test_layout.setContentsMargins(0, 0, 0, 0)
        self.test_lookback_days = QSpinBox()
        self.test_lookback_days.setRange(1, 365)
        self.test_lookback_days.setSuffix(' days')
        self.test_lookback_days.setValue(self.settings['test_lookback_days'])
        self.field(test_layout, 'Test article timeframe', self.test_lookback_days,
                   'Look back 1 to 365 days for Preview, Test AI, and Collect test articles. Saves immediately. Normal collection and automatic checks use 48 hours.')
        test_layout.addWidget(label('Look back this many days for Preview, Test AI, and Collect test articles. Only articles still available in publisher feeds can be retrieved. Collect new and automatic checks keep the 48-hour window.', 'muted'))
        self.test_mode = named(QCheckBox('Allow resends for manual tests'), 'Allow resends for manual tests',
                               'Enables Collect test articles with the selected test timeframe and Dashboard limit per source. Automatic checks always skip delivered articles. Off each time the app opens.')
        test_layout.addWidget(self.test_mode)
        developer.addWidget(self.test_controls)
        page.addStretch()

    def developer_mode_changed(self):
        self.update_developer_mode()
        self.save_preferences()

    def update_developer_mode(self):
        enabled = self.developer_mode.isChecked()
        if not enabled:
            self.test_mode.setChecked(False)
            if self.tabs.currentIndex() == 5:
                self.focus_page(4)
        self.tabs.setTabVisible(5, enabled)
        self.preview_button.setVisible(enabled)
        self.ai_test_button.setVisible(enabled)
        self.test_controls.setVisible(enabled)
        if enabled:
            self.preview_panel.refresh()
        self.update_test_mode()

    def update_test_mode(self):
        testing = self.test_mode.isChecked()
        self.send_button.setText('Collect test articles' if testing else 'Collect new')
        self.preview_button.setText('Preview test articles' if testing else 'Preview')
        mode = 'DEV MODE: resends allowed' if testing else 'Skip previously delivered articles'
        window = f'{self.test_lookback_days.value()} days' if testing else '48 hours'
        self.collection_description.setText(f'Check all enabled sources for articles published in the last {window}.')
        self.test_status.setText(f'{mode}. Up to {self.per_source_limit.value()} per source; newest first, last {window}.')
        self.preview_button.setToolTip(f'Preview eligible articles from the last {self.test_lookback_days.value()} days using the selected scope and per-source limit.')
        self.ai_test_button.setToolTip(f'Test AI on an eligible article from the last {self.test_lookback_days.value()} days.')
        webhook = self.webhook_entry.text().strip() if hasattr(self, 'webhook_entry') else self.settings['webhook']
        self.destination.setText('Publish to Discord' if webhook else 'Publish in Results')

    def _connection(self, page):
        form = self.card(page, 'Connect your workspace', 'Credentials are encrypted for your Windows account. Each provider keeps its own key and model.')
        self.webhook_entry = QLineEdit(self.settings['webhook'])
        self.webhook_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.field(form, 'Discord webhook URL', self.webhook_entry, 'Optional. Leave blank to publish articles in the Results tab. Add a webhook to send to Discord.')
        self.webhook_entry.setPlaceholderText('Optional — leave blank to publish in Results')
        self.webhook_entry.textChanged.connect(self.update_test_mode)
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
        page.addWidget(label('Developer previews do not publish articles or change delivery history.', 'muted'))
        self.preview_panel = ReportPanel(self.root / 'preview', preview=True)
        page.addWidget(self.preview_panel, 1)

    def text_area(self, name, description):
        widget = named(QPlainTextEdit(), name, description)
        widget.setReadOnly(True)
        widget.setTabChangesFocus(True)
        widget.setMinimumHeight(120)
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
        if not self.tabs.isTabVisible(index):
            return
        self.tabs.setCurrentIndex(index)
        self.tabs.tabBar().setFocus()

    def ensure_focus_visible(self, old, current):
        self.scroll_to_focus()
        # Wrapping form rows can settle after the focus event during scaling.
        self.focus_scroll_timer.start(0)

    def scroll_to_focus(self):
        current = self.qapp.focusWidget()
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
                points = max(9, points)
            font.setPointSizeF(points * scale)
            self.setFont(font)
            if self.high_contrast or mode == 'system':
                self.qapp.setStyleSheet('')
                self.qapp.setPalette(system if self.high_contrast else self.system_palette)
            else:
                self.qapp.setPalette(palette_for(THEMES[mode]))
                self.qapp.setStyleSheet(stylesheet(mode, points * scale))
            for panel in (self.results_panel, self.preview_panel):
                panel.update_link_colors(self.qapp.palette().color(QPalette.ColorRole.Link))
            self.source_list.verticalHeader().setDefaultSectionSize(max(30, int(points * scale * 2.8)))
            self.update_compact_header()
        finally:
            self._applying_theme = False

    def update_compact_header(self):
        compact = self.width() < 800 or self.scale_combo.currentData() >= 150
        self.radar.setVisible(not compact)
        for name in ('results_panel', 'preview_panel'):
            if hasattr(self, name):
                getattr(self, name).set_compact(compact)
        if hasattr(self, 'filters_card'):
            wide = self.width() >= 900 and self.scale_combo.currentData() == 100
            self.dashboard_grid.removeWidget(self.batch_card)
            self.dashboard_grid.removeWidget(self.auto_card)
            self.dashboard_grid.removeWidget(self.filters_card)
            self.dashboard_grid.addWidget(self.batch_card, 0, 0)
            self.dashboard_grid.addWidget(self.auto_card, 1, 0)
            self.dashboard_grid.addWidget(self.filters_card, 0 if wide else 2, 1 if wide else 0, 2 if wide else 1, 1)
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
                               ('close_to_tray', self.close_to_tray.isChecked()), ('pause_log', self.pause_log.isChecked()),
                               ('developer_mode', self.developer_mode.isChecked()), ('per_source_limit', self.per_source_limit.value()),
                               ('sector_scope', self.sector_scope.currentData()), ('test_lookback_days', self.test_lookback_days.value())):
                saved[key] = self.settings[key] = value
            saved.update(self.selected_filters())
            self.settings.update(self.selected_filters())
            save_settings(self.root, saved)
            self.status_message('Settings saved.')
        except Exception:
            self.status_message('Preference changed for this session. Unable to save it to the app data folder.')

    def apply_scope(self):
        selected = self.selected_filters()
        self.results_panel.set_filters(selected)
        self.preview_panel.set_filters(selected)
        count = sum(bool(value) for value in selected.values())
        self.filter_summary.setText(f'{count} active scope' + ('s' if count != 1 else '') + ' — all must match' if count else 'All articles — no scope filters')
        self.filter_summary.setToolTip(scopes.describe(selected))

    def selected_filters(self):
        return {key: combo.currentData() for key, combo in self.scope_controls.items()}

    def reset_filters(self):
        for combo in self.scope_controls.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.scope_changed()

    def scope_changed(self):
        self.apply_scope()
        self.save_preferences()
        if self.process:
            self.status_message('Filters saved for the next task. The active task keeps its original filters.')

    def show_scope_keywords(self):
        selected = self.selected_filters()
        dialog = QDialog(self)
        dialog.setWindowTitle('Selected filter keywords')
        dialog.resize(600, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('All selected scopes must match', 'heading'))
        text = self.text_area('Scope keyword list', 'Read-only keywords used to filter article title and body before AI analysis.')
        text.setPlainText('\n\n'.join(scopes.LABELS[key] + ': ' + scopes.CHOICES[key][value] + '\n' + scopes.keywords(key, value)
                                    for key, value in selected.items()))
        layout.addWidget(text, 1)
        layout.addWidget(label('OR separates alternatives; + requires all terms in the article. Words and phrases use word boundaries and common plurals. Parentheses require the stated context.', 'muted'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

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
            'Article reader: Tab through article, CVE, and ATT&CK links; Enter opens the focused link in your browser.\n'
            'Ctrl+1 to Ctrl+5: Dashboard, Connection, Sources, Results, Preferences.\n'
            'Ctrl+6: Previews (Dev mode only).\n'
            'Ctrl+7: focus article filters on the Dashboard.\n'
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
                     'profiles': deepcopy(self.profiles), 'per_source_limit': self.per_source_limit.value(),
                     **self.selected_filters(),
                     'interval_minutes': self.interval.value(), 'close_to_tray': self.close_to_tray.isChecked(),
                     'theme': self.theme_combo.currentData(), 'text_scale': self.scale_combo.currentData(),
                     'developer_mode': self.developer_mode.isChecked(), 'pause_log': self.pause_log.isChecked(),
                     'test_lookback_days': self.test_lookback_days.value()}
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
        if action in ('ai', 'preview', 'test', 'test-preview') and not self.developer_mode.isChecked():
            self.status_message('Enable Dev mode in Preferences to use previews and AI tests.')
            return False
        if action in ('test', 'test-preview') and not self.test_mode.isChecked():
            self.status_message('Enable Allow resends in Preferences to collect test articles using the selected test timeframe.')
            return False
        if self.process or self.quit_pending or not self.save():
            return False
        value = self.settings
        error, field = None, self.webhook_entry
        if action == 'webhook' and not value['webhook']:
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
        if time.monotonic() - self.last_results_check > 2:
            self.last_results_check = time.monotonic()
            self.results_panel.refresh()
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
        self.results_panel.refresh()
        if self.developer_mode.isChecked():
            self.preview_panel.refresh()

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
        self.focus_scroll_timer.stop()
        if self.tray:
            self.tray.stop()
        self.force_close = True
        self.qapp.removeEventFilter(self)
        self.qapp.focusChanged.disconnect(self.ensure_focus_visible)
        self.qapp.styleHints().colorSchemeChanged.disconnect(self.platform_theme_changed)
        self.close()
        if self.quit_on_exit:
            self.qapp.quit()

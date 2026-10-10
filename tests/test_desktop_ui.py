"""Headless widget/keyboard/accessibility tests. No OS input or live network calls."""
from importlib.util import find_spec
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from osint_digest.desktop import settings as settings
from osint_digest.core.sources import make_source

HAS_GUI = find_spec('PySide6') is not None
if HAS_GUI:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt, QEvent, QCoreApplication
    from PySide6.QtGui import QAccessible, QFont, QFontDatabase, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit
    from osint_digest.desktop.ui import DigestApp
    from osint_digest.desktop.theme import THEMES, contrast

_QAPP = None


@unittest.skipUnless(HAS_GUI and os.name == 'nt', 'Install desktop dependencies on Windows for GUI tests')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _QAPP
        _QAPP = QApplication.instance() or QApplication([])
        _QAPP.setQuitOnLastWindowClosed(False)
        # The offscreen plugin has no platform font database. Register local test fonts.
        for name in ('segoeui.ttf', 'seguisb.ttf', 'segoeuib.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
        _QAPP.setFont(QFont('Segoe UI', 11))
        cls.system_palette = QPalette(_QAPP.palette())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = DigestApp(Path(self.temp.name), discover_models=False, quit_on_exit=False)
        self.app.resize(1160, 940)
        self.app.show()
        _QAPP.processEvents()

    def tearDown(self):
        self.app.process = None
        if self.app.alive:
            self.app.exit_app()
        self.app.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _QAPP.setStyleSheet('')
        _QAPP.setPalette(self.system_palette)
        self.temp.cleanup()

    def test_provider_keys_models_and_stale_responses_are_isolated(self):
        app = self.app
        app.key_entry.setText('gemini-secret')
        app.model_combo.setCurrentText('gemini-saved')
        with patch.object(app, 'refresh_models'):
            app.provider.setCurrentIndex(app.provider.findData('openai'))
            self.assertEqual(app.key_entry.text(), '')
            self.assertEqual(app.model_combo.currentText(), '')
            app.key_entry.setText('openai-secret')
            app.model_combo.setCurrentText('gpt-saved')
            app.events.put((('gemini', 'gemini-secret'), ['gemini-other'], None))
            app.handle_events()
            self.assertEqual(app.model_combo.currentText(), 'gpt-saved')
            app.provider.setCurrentIndex(app.provider.findData('gemini'))
        self.assertEqual(app.key_entry.text(), 'gemini-secret')
        self.assertEqual(app.model_combo.currentText(), 'gemini-saved')
        self.assertTrue(app.save())
        self.assertEqual(settings.load_settings(app.root)['profiles']['openai']['model'], 'gpt-saved')

    def test_models_refresh_preserves_saved_id_on_error(self):
        app = self.app
        app.key_entry.setText('gemini-secret')
        app.model_combo.setCurrentText('gemini-saved')
        app.events.put((('gemini', 'gemini-secret'), ['gemini-new', 'gemini-saved'], None))
        app.handle_events()
        self.assertEqual(app.model_combo.count(), 2)
        app.events.put((('gemini', 'gemini-secret'), [], 'HTTPError HTTP 401'))
        app.handle_events()
        self.assertEqual(app.model_combo.currentText(), 'gemini-saved')
        self.assertIn('401', app.model_status.text())

    def test_custom_sources_reorder_disable_and_persist(self):
        app = self.app
        app.sources.append(make_source('Custom', 'https://example.com/rss', 'www.example.com', app.sources))
        app.rebuild_sources(len(app.sources) - 1)
        app.move_source(-1)
        app.toggle_source()
        self.assertTrue(app.save())
        saved = json.loads((app.root / 'sources.json').read_text())
        self.assertEqual(saved[-2]['name'], 'Custom')
        self.assertFalse(saved[-2]['enabled'])

    def test_worker_routes_action_displays_log_and_schedules_next_check(self):
        app = self.app
        app.provider.setCurrentIndex(app.provider.findData('none'))
        app.webhook_entry.setText('https://discord.com/api/webhooks/123/fake')
        process = Mock()
        process.poll.return_value = None
        with patch('osint_digest.desktop.ui.subprocess.Popen', return_value=process) as launch:
            app.toggle_monitor()
            self.assertTrue(app.monitoring)
            button = QAccessible.queryAccessibleInterface(app.auto_button)
            self.assertEqual(button.text(QAccessible.Text.Name), 'Stop automatic checks')
            self.assertEqual(launch.call_args.args[0][-2:], ['--worker', 'new'])
            self.assertNotIn('fake', ' '.join(launch.call_args.args[0]))
            (app.root / 'activity.log').write_text('Posted: 2; AI summaries: 0\n')
            process.poll.return_value = 0
            app.poll()
            self.assertIsNone(app.process)
            self.assertIn('Posted: 2', app.activity.toPlainText())
            self.assertGreater(app.next_check, time.time())
            app.toggle_monitor()
            self.assertFalse(app.monitoring)
            self.assertEqual(button.text(QAccessible.Text.Name), 'Start automatic checks')

    def test_missing_connection_focuses_field_and_does_not_start_worker(self):
        with patch('osint_digest.desktop.ui.subprocess.Popen') as launch:
            self.assertFalse(self.app.start('new'))
        launch.assert_not_called()
        self.assertEqual(self.app.tabs.currentIndex(), 1)
        self.assertIn('webhook', self.app.status.text())
        self.assertIs(_QAPP.focusWidget(), self.app.webhook_entry)

    def test_test_mode_is_opt_in_accessible_and_manual_only(self):
        app = self.app
        self.assertFalse(app.test_mode.isChecked())
        self.assertFalse(app.batch_size.isEnabled())
        self.assertIn('no article limit', app.test_status.text())
        with patch.object(app, 'start', return_value=True) as start:
            app.send_button.click()
            self.assertEqual(start.call_args.args, ('new',))
            app.preview_button.click()
            self.assertEqual(start.call_args.args, ('preview',))
            app.test_mode.setChecked(True)
            self.assertTrue(app.batch_size.isEnabled())
            interface = QAccessible.queryAccessibleInterface(app.send_button)
            self.assertEqual(interface.text(QAccessible.Text.Name), 'Send test articles')
            app.send_button.click()
            self.assertEqual(start.call_args.args, ('test',))
            app.preview_button.click()
            self.assertEqual(start.call_args.args, ('test-preview',))
            app.toggle_monitor()
            self.assertEqual(start.call_args.args, ('new',))
        app.test_mode.setChecked(False)
        with patch('osint_digest.desktop.ui.subprocess.Popen') as launch:
            self.assertFalse(app.start('test'))
            launch.assert_not_called()


    def test_tray_close_preserves_checks_and_restore(self):
        app = self.app
        app.monitoring = True
        with patch('osint_digest.desktop.ui.Tray') as tray:
            tray.return_value.start.return_value = True
            app.close()
            self.assertFalse(app.isVisible())
            self.assertTrue(app.monitoring)
            app.restore_window()
            self.assertTrue(app.isVisible())
            self.assertTrue(app.monitoring)

    def test_tray_unavailable_keeps_taskbar_window(self):
        with patch('osint_digest.desktop.ui.Tray') as tray:
            tray.return_value.start.return_value = False
            self.app.hide_to_tray()
        self.assertTrue(self.app.isMinimized())
        self.assertIn('taskbar', self.app.status.text())

    def test_exit_preserves_active_task_and_stops_future_checks(self):
        self.app.process = Mock()
        self.app.monitoring = True
        self.app.exit_app()
        self.assertTrue(self.app.quit_pending)
        self.assertFalse(self.app.monitoring)
        self.assertTrue(self.app.alive)
        self.app.process.terminate.assert_not_called()
        self.assertFalse(self.app.start('new'))

    def test_preferences_persist_without_saving_uncommitted_credentials(self):
        self.app.key_entry.setText('unsaved-secret')
        self.app.theme_combo.setCurrentIndex(self.app.theme_combo.findData('light'))
        self.app.scale_combo.setCurrentIndex(self.app.scale_combo.findData(150))
        saved = settings.load_settings(self.app.root)
        self.assertEqual((saved['theme'], saved['text_scale']), ('light', 150))
        self.assertEqual(saved['api_key'], '')
        self.assertEqual(self.app.key_entry.text(), 'unsaved-secret')

    def test_theme_text_control_and_focus_contrast(self):
        for name, colors in THEMES.items():
            for text in ('text', 'muted', 'accent', 'error'):
                for background in ('background', 'card', 'panel', 'field'):
                    with self.subTest(theme=name, text=text, background=background):
                        self.assertGreaterEqual(contrast(colors[text], colors[background]), 4.5)
            self.assertGreaterEqual(contrast(colors['on_accent'], colors['accent']), 4.5)
            for token in ('border', 'focus'):
                for background in ('background', 'card', 'panel', 'field'):
                    self.assertGreaterEqual(contrast(colors[token], colors[background]), 3)

    def test_accessible_names_roles_and_password_state(self):
        for widget, name in ((self.app.webhook_entry, 'Discord webhook URL'), (self.app.key_entry, 'AI API key'),
                              (self.app.provider, 'Summary provider'), (self.app.model_combo, 'Model'),
                              (self.app.source_list, 'Publisher sources'), (self.app.activity, 'Activity log')):
            interface = QAccessible.queryAccessibleInterface(widget)
            self.assertTrue(interface.isValid())
            self.assertEqual(interface.text(QAccessible.Text.Name), name)
        key = QAccessible.queryAccessibleInterface(self.app.key_entry)
        self.assertEqual(key.role(), QAccessible.Role.EditableText)
        self.assertTrue(key.state().passwordEdit)
        self.app.show_keys.setChecked(True)
        self.assertFalse(key.state().passwordEdit)
        self.app.show_keys.setChecked(False)
        self.app.provider.setCurrentIndex(self.app.provider.findData('none'))
        self.assertTrue(key.state().disabled)

    def test_keyboard_navigation_shortcuts_and_source_toggle(self):
        app = self.app
        app.activateWindow()
        app.webhook_entry.setFocus()
        _QAPP.processEvents()
        QTest.keyClick(app.webhook_entry, Qt.Key.Key_Tab)
        self.assertIs(_QAPP.focusWidget(), app.provider)
        QTest.keyClick(app.provider, Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(app.tabs.currentIndex(), 2)
        app.source_list.selectRow(0)
        app.source_list.setFocus()
        original = app.sources[0]['enabled']
        QTest.keyClick(app.source_list, Qt.Key.Key_Space)
        self.assertNotEqual(app.sources[0]['enabled'], original)

    def test_text_doubles_without_compounding_and_small_windows_scroll(self):
        app = self.app
        baseline = app.key_entry.font().pointSizeF()
        app.scale_combo.setCurrentIndex(app.scale_combo.findData(200))
        app.resize(640, 480)
        for _ in range(3):
            _QAPP.processEvents()
        self.assertAlmostEqual(app.key_entry.font().pointSizeF(), baseline * 2, delta=.2)
        self.assertGreater(app.workspace_scroll.verticalScrollBar().maximum(), 0)
        app.key_entry.setFocus()
        _QAPP.processEvents()
        viewport = app.workspace_scroll.viewport()
        center = app.key_entry.mapTo(viewport, app.key_entry.rect().center())
        self.assertTrue(viewport.rect().contains(center), 'Focused field must scroll into view')

    def test_windows_contrast_theme_overrides_custom_styles(self):
        with patch('osint_digest.desktop.ui.high_contrast_enabled', return_value=True):
            self.app.apply_appearance()
            self.assertTrue(self.app.high_contrast)
            self.assertEqual(_QAPP.styleSheet(), '')
        self.app.apply_appearance()
        self.assertIn('border-radius', _QAPP.styleSheet())

    def test_pause_activity_updates_preserves_review_then_catches_up(self):
        app = self.app
        app.last_log = ''
        app.set_text(app.activity, 'Review this text')
        (app.root / 'activity.log').write_text('New result')
        app.pause_log.setChecked(True)
        app.read_log()
        self.assertEqual(app.activity.toPlainText(), 'Review this text')
        with patch('osint_digest.desktop.ui.subprocess.Popen', return_value=Mock()):
            self.assertTrue(app.start('feeds'))
        self.assertEqual(app.activity.toPlainText(), 'Review this text')
        (app.root / 'activity.log').write_text('New result')
        app.pause_log.setChecked(False)
        app.read_log()
        self.assertEqual(app.activity.toPlainText(), 'New result')


if __name__ == '__main__':
    unittest.main()

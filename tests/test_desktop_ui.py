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
    from PySide6.QtCore import Qt, QEvent, QCoreApplication, QUrl
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
        self.assertIn('AI API key', self.app.status.text())
        self.assertIs(_QAPP.focusWidget(), self.app.key_entry)

    def test_test_mode_is_opt_in_accessible_and_manual_only(self):
        app = self.app
        self.assertFalse(app.test_mode.isChecked())
        self.assertTrue(app.per_source_limit.isEnabled())
        self.assertIn('Up to 5 per source', app.test_status.text())
        app.developer_mode.setChecked(True)
        with patch.object(app, 'start', return_value=True) as start:
            app.send_button.click()
            self.assertEqual(start.call_args.args, ('new',))
            app.preview_button.click()
            self.assertEqual(start.call_args.args, ('preview',))
            app.test_mode.setChecked(True)
            self.assertTrue(app.per_source_limit.isEnabled())
            interface = QAccessible.queryAccessibleInterface(app.send_button)
            self.assertEqual(interface.text(QAccessible.Text.Name), 'Collect test articles')
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

    def test_per_source_limit_is_visible_accessible_and_persists_without_dev_mode(self):
        app = self.app
        self.assertFalse(app.developer_mode.isChecked())
        self.assertTrue(app.pages[0][0].widget().isAncestorOf(app.per_source_limit))
        self.assertTrue(app.per_source_limit.isVisible())
        interface = QAccessible.queryAccessibleInterface(app.per_source_limit)
        self.assertEqual(interface.text(QAccessible.Text.Name), 'Articles per source')
        app.per_source_limit.setValue(10)
        self.assertEqual(settings.load_settings(app.root)['per_source_limit'], 10)
        self.assertIn('10 per source', app.test_status.text())
        self.assertIn('48 hours', app.test_status.text())

    def test_dev_timeframe_is_accessible_persists_and_never_changes_normal_collection(self):
        app = self.app
        app.focus_page(4)
        self.assertFalse(app.test_lookback_days.isVisible())
        app.developer_mode.setChecked(True)
        self.assertTrue(app.test_lookback_days.isVisible())
        interface = QAccessible.queryAccessibleInterface(app.test_lookback_days)
        self.assertEqual(interface.text(QAccessible.Text.Name), 'Test article timeframe')
        self.assertEqual((app.test_lookback_days.minimum(), app.test_lookback_days.maximum()), (1, 365))
        app.key_entry.setText('unsaved-secret')
        app.test_lookback_days.setValue(30)
        saved = settings.load_settings(app.root)
        self.assertEqual(saved['test_lookback_days'], 30)
        self.assertEqual(saved['api_key'], '')
        self.assertIn('48 hours', app.test_status.text())
        app.test_mode.setChecked(True)
        self.assertIn('30 days', app.test_status.text())
        self.assertIn('30 days', app.collection_description.text())
        with patch.object(app, 'start', return_value=True) as start:
            app.toggle_monitor()
            self.assertEqual(start.call_args.args, ('new',))
        app.developer_mode.setChecked(False)
        self.assertFalse(app.test_mode.isChecked())
        self.assertFalse(app.test_lookback_days.isVisible())
        self.assertIn('48 hours', app.test_status.text())


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

    def test_preferences_own_view_controls_and_dev_mode_gates_all_preview_entry_points(self):
        app = self.app
        preferences = app.pages[4][0].widget()
        for widget in (app.theme_combo, app.scale_combo, app.pause_log, app.close_to_tray, app.developer_mode):
            self.assertTrue(preferences.isAncestorOf(widget))
        self.assertFalse(app.tabs.isTabVisible(5))
        self.assertTrue(app.preview_button.isHidden())
        self.assertTrue(app.ai_test_button.isHidden())
        app.focus_page(5)
        self.assertNotEqual(app.tabs.currentIndex(), 5)
        with patch('osint_digest.desktop.ui.subprocess.Popen') as launch:
            for action in ('preview', 'test', 'test-preview', 'ai'):
                self.assertFalse(app.start(action))
            launch.assert_not_called()
        app.developer_mode.setChecked(True)
        self.assertTrue(app.tabs.isTabVisible(5))
        self.assertFalse(app.preview_button.isHidden())
        self.assertTrue(settings.load_settings(app.root)['developer_mode'])
        app.test_mode.setChecked(True)
        app.focus_page(5)
        app.developer_mode.setChecked(False)
        self.assertEqual(app.tabs.currentIndex(), 4)
        self.assertFalse(app.test_mode.isChecked())
        self.assertFalse(settings.load_settings(app.root)['developer_mode'])

    def test_blank_webhook_allows_manual_and_automatic_collection(self):
        app = self.app
        app.provider.setCurrentIndex(app.provider.findData('none'))
        self.assertEqual(app.webhook_entry.text(), '')
        self.assertEqual(app.destination.text(), 'Publish in Results')
        process = Mock()
        process.poll.return_value = 0
        with patch('osint_digest.desktop.ui.subprocess.Popen', return_value=process) as launch:
            self.assertTrue(app.start('new'))
            self.assertEqual(launch.call_args.args[0][-2:], ['--worker', 'new'])
            app.poll()
            app.toggle_monitor()
            self.assertTrue(app.monitoring)
        app.webhook_entry.setText('https://discord.com/api/webhooks/123/fake')
        self.assertEqual(app.destination.text(), 'Publish to Discord')

    def test_results_reader_refresh_search_and_selection_survive_new_articles(self):
        app = self.app
        report = {'source': 'Example', 'title': 'First article', 'url': 'https://example.com/one',
                  'published': 'Wed, 07 Oct 2026 22:00:16 +0000', 'publisher_excerpt': 'Version 10.1.20 fixes the issue.',
                  'cves': ['CVE-2026-1234'], 'attack_ids': ['T1059.001'],
                  'iocs': [{'type': 'domain', 'value': 'evil.example'}]}
        path = app.root / 'results/one.json'
        settings.atomic_json(path, report)
        app.refresh_reports()
        panel = app.results_panel
        self.assertEqual(panel.list.count(), 1)
        self.assertIn('Version 10.1.20', panel.text.toPlainText())
        self.assertIn('CVE-2026-1234', panel.text.toPlainText())
        self.assertIn('T1059.001', panel.text.toPlainText())
        self.assertIn('evil[.]example', panel.text.toPlainText())
        self.assertTrue(panel.open_button.isEnabled())
        settings.atomic_json(app.root / 'results/two.json', {**report, 'title': 'Second article'})
        settings.atomic_json(app.root / 'preview/dev.json', {**report, 'title': 'Developer preview'})
        (app.root / 'results/broken.json').write_text('{broken')
        app.refresh_reports()
        self.assertEqual(panel.list.count(), 2)
        self.assertEqual(panel.current_path, path)
        self.assertIn('First article', panel.text.toPlainText())
        panel.search.setText('second')
        self.assertEqual(panel.list.count(), 1)
        self.assertIn('Second article', panel.text.toPlainText())
        panel.search.setText('no match')
        self.assertEqual(panel.list.count(), 0)
        self.assertEqual(panel.text.toPlainText(), 'No matching articles.')
        self.assertFalse(panel.open_button.isEnabled())

    def test_article_renderer_escapes_markup_and_formats_rss_dates(self):
        from osint_digest.desktop.reports import article_html, display_time
        html = article_html({'title': '<img src="https://example.com/track">',
                             'source': '<script>bad()</script>', 'publisher_excerpt': '<b>literal</b>'})
        self.assertNotIn('<img', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;b&gt;literal&lt;/b&gt;', html)
        self.assertEqual(display_time('Wed, 07 Oct 2026 22:00:16 +0000'), display_time('2026-10-07T22:00:16Z'))

    def test_scope_is_accessible_persists_and_filters_results_and_previews(self):
        from osint_digest.core.sectors import CATALOG_VERSION
        app = self.app
        for folder in ('results', 'preview'):
            for name, words in (('Education', {'education': ['cloud']}), ('Finance', {'financial': ['bank']})):
                settings.atomic_json(app.root / folder / (name + '.json'), {
                    'title': name, 'sector_catalog': CATALOG_VERSION, 'sector_matches': words})
        app.refresh_reports()
        self.assertEqual(app.results_panel.list.count(), 2)
        self.assertEqual(app.sector_scope.count(), 25)
        interface = QAccessible.queryAccessibleInterface(app.sector_scope)
        self.assertEqual(interface.text(QAccessible.Text.Name), 'Sector scope')
        app.key_entry.setText('unsaved-secret')
        app.sector_scope.setCurrentIndex(app.sector_scope.findData('education'))
        self.assertEqual(settings.load_settings(app.root)['sector_scope'], 'education')
        self.assertEqual(settings.load_settings(app.root)['api_key'], '')
        for panel in (app.results_panel, app.preview_panel):
            panel.refresh()
            self.assertEqual(panel.list.count(), 1)
            self.assertEqual(panel.current_report['title'], 'Education')
        app.sector_scope.setCurrentIndex(app.sector_scope.findData(''))
        self.assertEqual(app.results_panel.list.count(), 2)
        self.assertEqual(len(list((app.root / 'results').glob('*.json'))), 2)

    def test_seven_filter_selectors_combine_persist_and_reset_without_deleting_reports(self):
        from osint_digest.core import scopes
        app = self.app
        app.focus_page(6)
        selected = {'sector_scope': 'education', 'actor_scope': 'nation_state', 'social_scope': 'phishing',
                    'access_scope': 'zero_day', 'malware_scope': 'data_breach',
                    'other_scope': 'lateral_movement', 'education_scope': 'university_phishing'}
        for name, text in (('match', 'APT phishing and a zero-day caused a university data breach after lateral movement.'),
                           ('excluded', 'A university software patch.')):
            for folder in ('results', 'preview'):
                settings.atomic_json(app.root / folder / (name + '.json'), {
                    'title': name, 'filter_catalog': scopes.CATALOG_VERSION, 'filter_matches': scopes.classify(text)})
        app.refresh_reports()
        app.preview_panel.refresh()
        self.assertEqual(len(app.scope_controls), 7)
        app.key_entry.setText('unsaved-secret')
        for key, option in selected.items():
            combo = app.scope_controls[key]
            self.assertEqual(combo.currentText(), 'All')
            self.assertTrue(app.pages[6][0].widget().isAncestorOf(combo))
            self.assertEqual(QAccessible.queryAccessibleInterface(combo).text(QAccessible.Text.Name),
                             'Sector scope' if key == 'sector_scope' else scopes.LABELS[key])
            combo.setCurrentIndex(combo.findData(option))
        saved = settings.load_settings(app.root)
        self.assertEqual(scopes.selection(saved), selected)
        self.assertEqual(saved['api_key'], '')
        self.assertIn('7 active scopes', app.filter_summary.text())
        for panel in (app.results_panel, app.preview_panel):
            self.assertEqual(panel.list.count(), 1)
            self.assertEqual(panel.current_report['title'], 'match')
        app.scope_controls['social_scope'].setCurrentIndex(app.scope_controls['social_scope'].findData('vishing'))
        self.assertEqual(app.results_panel.list.count(), 0)
        app.reset_filters()
        self.assertEqual(scopes.selection(settings.load_settings(app.root)), scopes.DEFAULTS)
        self.assertEqual(app.results_panel.list.count(), 2)
        self.assertEqual(len(list((app.root / 'results').glob('*.json'))), 2)

    def test_filters_have_keyboard_shortcut_and_dropdown_navigation(self):
        app = self.app
        app.activateWindow()
        app.focus_page(0)
        app.send_button.setFocus()
        _QAPP.processEvents()
        QTest.keyClick(app.send_button, Qt.Key.Key_7, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(app.tabs.currentIndex(), 6)
        app.sector_scope.setFocus()
        _QAPP.processEvents()
        QTest.keyClick(app.sector_scope, Qt.Key.Key_Tab)
        self.assertIs(_QAPP.focusWidget(), app.scope_controls['actor_scope'])
        QTest.keyClick(_QAPP.focusWidget(), Qt.Key.Key_Down)
        self.assertEqual(settings.load_settings(app.root)['actor_scope'], 'ransomware')

    def test_large_text_filters_scroll_last_focused_selector_into_view(self):
        app = self.app
        app.scale_combo.setCurrentIndex(app.scale_combo.findData(200))
        app.resize(640, 480)
        app.focus_page(6)
        combo = app.scope_controls['education_scope']
        combo.setFocus()
        for _ in range(3):
            _QAPP.processEvents()
        point = combo.mapTo(app, combo.rect().center())
        self.assertTrue(app.rect().contains(point), 'The focused scope must remain visible after form rows wrap')

    def linked_report(self):
        settings.atomic_json(self.app.root / 'results/links.json', {
            'title': 'Linked report', 'url': 'https://example.com/story?a=1&b=2',
            'cves': ['CVE-2026-1234', 'cve-2026-1234', '<invalid>'],
            'attack_ids': ['T1059', 'T1059.001', 'T1059.001/bad'],
            'iocs': [{'type': 'domain', 'value': 'evil.example'}]})
        self.app.refresh_reports()
        self.app.focus_page(3)
        _QAPP.processEvents()
        return self.app.results_panel

    def test_source_cve_and_technique_links_open_default_browser_by_mouse(self):
        panel = self.linked_report()
        targets = [('Read original article', 'https://example.com/story?a=1&b=2'),
                   ('CVE-2026-1234', 'https://www.cve.org/CVERecord?id=CVE-2026-1234'),
                   ('T1059', 'https://attack.mitre.org/techniques/T1059/'),
                   ('T1059.001', 'https://attack.mitre.org/techniques/T1059/001/')]
        with patch('osint_digest.desktop.reports.QDesktopServices.openUrl', return_value=True) as open_url:
            for label, target in targets:
                with self.subTest(label=label):
                    cursor = panel.text.document().find(label)
                    self.assertFalse(cursor.isNull())
                    cursor.setPosition(cursor.selectionStart() + 2)
                    panel.text.setTextCursor(cursor)
                    panel.text.ensureCursorVisible()
                    _QAPP.processEvents()
                    QTest.mouseClick(panel.text.viewport(), Qt.MouseButton.LeftButton,
                                     pos=panel.text.cursorRect(cursor).center())
                    self.assertEqual(open_url.call_args.args[0].toString(), target)
            self.assertEqual(open_url.call_count, 4)
            panel.open_button.click()
            self.assertEqual(open_url.call_args.args[0].toString(), targets[0][1])
            before = open_url.call_count
            for url in ('file:///C:/Windows/system32/cmd.exe', 'https://evil.example', 'javascript:alert(1)'):
                panel.text.anchorClicked.emit(QUrl(url))
            self.assertEqual(open_url.call_count, before)
        self.assertIn('default browser', panel.link_status.text())
        self.assertNotIn('https://evil.example', panel.text.toHtml())

    def test_reader_links_are_keyboard_accessible(self):
        panel = self.linked_report()
        self.app.activateWindow()
        panel.list.setFocus()
        _QAPP.processEvents()
        QTest.keyClick(panel.list, Qt.Key.Key_Tab)
        self.assertIs(_QAPP.focusWidget(), panel.text)
        with patch('osint_digest.desktop.reports.QDesktopServices.openUrl', return_value=True) as open_url:
            for index in range(4):
                QTest.keyClick(_QAPP.focusWidget(), Qt.Key.Key_Tab)
                QTest.keyClick(_QAPP.focusWidget(), Qt.Key.Key_Return)
                self.assertEqual(open_url.call_count, index + 1)
            self.assertEqual([call.args[0].toString() for call in open_url.call_args_list], [
                'https://example.com/story?a=1&b=2', 'https://www.cve.org/CVERecord?id=CVE-2026-1234',
                'https://attack.mitre.org/techniques/T1059/', 'https://attack.mitre.org/techniques/T1059/001/'])

    def test_link_failure_has_feedback_and_invalid_source_is_disabled(self):
        panel = self.linked_report()
        with patch('osint_digest.desktop.reports.QDesktopServices.openUrl', return_value=False):
            panel.open_button.click()
        self.assertIn('Unable to open', panel.link_status.text())
        from osint_digest.desktop.reports import safe_article_url
        for url in ('https://example.com:bad', 'https://user:pass@example.com/', 'javascript:alert(1)', None):
            self.assertIsNone(safe_article_url({'url': url}))
        settings.atomic_json(self.app.root / 'results/links.json', {'title': 'Bad link', 'url': 'file:///C:/bad'})
        self.app.refresh_reports()
        self.assertFalse(panel.open_button.isEnabled())

    def test_existing_links_follow_theme_changes_without_resetting_article(self):
        panel = self.linked_report()
        selected = panel.current_path
        for theme in ('light', 'dark'):
            self.app.theme_combo.setCurrentIndex(self.app.theme_combo.findData(theme))
            cursor = panel.text.document().find('CVE-2026-1234')
            self.assertEqual(cursor.charFormat().foreground().color().name(), THEMES[theme]['accent'].lower())
            self.assertTrue(cursor.charFormat().fontUnderline())
            self.assertEqual(panel.current_path, selected)

    def test_compact_dashboard_keeps_primary_controls_and_activity_visible(self):
        app = self.app
        app.resize(1040, 740)
        app.focus_page(0)
        _QAPP.processEvents()
        self.assertLess(app.send_button.height(), 44)
        viewport = app.pages[0][0].viewport()
        for control in (app.send_button, app.auto_button, app.activity):
            point = control.mapTo(viewport, control.rect().topLeft())
            self.assertTrue(viewport.rect().contains(point), 'Dashboard controls should fit without scrolling at default size')

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
        app.focus_page(1)
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
        app.focus_page(1)
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

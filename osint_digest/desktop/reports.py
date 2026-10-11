"""Local article reader. Publisher/model text is always rendered as escaped text."""
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
                               QListWidget, QListWidgetItem, QListView, QTextBrowser, QPushButton, QSplitter)

from osint_digest.core.collector import defang
from osint_digest.core.sectors import SCOPES, validate_scope
from osint_digest.core import scopes


def safe_article_url(report):
    try:
        url = report.get('url', '')
        parts = urlsplit(url)
        if (isinstance(url, str) and parts.scheme == 'https' and parts.hostname
                and not parts.username and not parts.password and parts.port in (None, 443)
                and not any(ord(c) < 32 for c in url)):
            return url
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def reference_links(report, key):
    pattern = r'CVE-\d{4}-\d{4,}' if key == 'cves' else r'T\d{4}(?:\.\d{3})?'
    values = report.get(key, [])
    if not isinstance(values, list):
        return []
    identifiers = sorted({value.upper() for value in values
                          if isinstance(value, str) and re.fullmatch(pattern, value, re.I)})
    return [(value, 'https://www.cve.org/CVERecord?id=' + value if key == 'cves' else
             'https://attack.mitre.org/techniques/' + value.replace('.', '/') + '/') for value in identifiers]


def display_time(value):
    if not value:
        return 'Not provided'
    try:
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return date.strftime('%b %d, %Y at %I:%M %p') + ' (timezone unspecified)'
        return date.astimezone().strftime('%b %d, %Y at %I:%M %p %Z')
    except (ValueError, TypeError, AttributeError, OverflowError):
        return str(value)


def article_html(report, preview=False):
    text = lambda value: escape(str(value))
    parts = [f'<h2>{text(report.get("title", "Untitled"))}</h2>',
             f'<p><b>{text(report.get("source", "Unknown source"))}</b><br>',
             f'Published: {text(display_time(report.get("published")))}']
    if report.get('saved_at'):
        parts.append(f'<br>Saved in app: {text(display_time(report["saved_at"]))}')
    parts.append('</p>')
    source_url = safe_article_url(report)
    if source_url:
        parts.append(f'<p><a href="{escape(source_url, quote=True)}">Read original article</a></p>')
    selected = report.get('filters')
    scope = report.get('sector_scope', '')
    if isinstance(selected, dict):
        selected = scopes.selection(selected)
        if any(selected.values()):
            parts.append(f'<p><b>Collection filters:</b> {text(scopes.describe(selected))}</p>')
            metadata = report.get('filter_matches', {})
            for key, value in selected.items():
                if value and isinstance(metadata, dict) and isinstance(metadata.get(key), dict):
                    parts.append(f'<p><b>{text(scopes.LABELS[key])} matched:</b> '
                                 + text(', '.join(metadata[key].get(value, []))) + '</p>')
    elif scope in SCOPES and scope:
        parts.append(f'<p><b>Sector scope:</b> {text(SCOPES[scope])}<br>Matched keywords: '
                     + text(', '.join((report.get('sector_matches') or {}).get(scope, []))) + '</p>')
    if preview:
        parts.append(f'<p>{text(report.get("ai_status", ""))}</p>')
    if report.get('analysis'):
        for key, title in (('summary', 'Summary'), ('affected', 'Affected'), ('actors', 'Actors / malware'),
                           ('techniques', 'Techniques'), ('actions', 'Recommendations')):
            claims = report['analysis'].get(key, [])
            parts.append(f'<h3>{title}</h3>')
            parts.append('<ul>' + ''.join(f'<li>{text(c["text"])}</li>' for c in claims) + '</ul>'
                         if claims else '<p>Not stated.</p>')
    else:
        parts.append(f'<h3>Publisher excerpt</h3><p>{text(report.get("publisher_excerpt", ""))}</p>')
    parts.append('<h3>References</h3>')
    for key, title in (('cves', 'CVEs'), ('attack_ids', 'MITRE ATT&amp;CK')):
        links = ', '.join(f'<a href="{escape(url, quote=True)}">{text(value)}</a>'
                          for value, url in reference_links(report, key))
        parts.append(f'<p><b>{title}:</b> {links or "None mentioned"}</p>')
    iocs = report.get('iocs', [])
    parts.append(f'<h3>IOC candidates ({len(iocs)})</h3>')
    for ioc in iocs:
        parts.append(f'<p><b>{text(ioc["type"])}</b>: <code>{text(defang(ioc["value"]))}</code></p>')
    if not iocs:
        parts.append('<p>None found.</p>')
    return ''.join(parts)


class ReportPanel(QWidget):
    def __init__(self, folder, preview=False):
        super().__init__()
        self.folder = Path(folder)
        self.preview = preview
        self.records = []
        self.fingerprint = None
        self.current_path = None
        self.current_report = None
        self.current_stamp = None
        self.sector_scope = ''
        self.filters = scopes.DEFAULTS.copy()
        title = 'Previews' if preview else 'Results'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search title or publisher')
        self.search.setAccessibleName(title + ' search')
        self.search.textChanged.connect(self.filter)
        self.count = QLabel('0 articles')
        self.count.setAccessibleName(title + ' count')
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.count)
        layout.addLayout(toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.list = QListWidget()
        self.list.setAccessibleName('Article previews' if preview else 'Published articles')
        self.list.setAccessibleDescription('Select an article with the arrow keys to read it.')
        self.list.setWordWrap(True)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setMinimumWidth(190)
        self.list.currentItemChanged.connect(self.show_selected)
        reader = QWidget()
        reader_layout = QVBoxLayout(reader)
        reader_layout.setContentsMargins(0, 0, 0, 0)
        self.text = QTextBrowser()
        self.text.setAccessibleName('Selected article preview' if preview else 'Selected published article')
        self.text.setAccessibleDescription('Read-only article. Tab moves through links and controls; Enter opens the focused link. Ctrl+A and Ctrl+C copy text.')
        self.text.setOpenLinks(False)
        self.text.setOpenExternalLinks(False)
        self.text.anchorClicked.connect(self.open_link)
        self.text.setTabChangesFocus(True)
        reader_layout.addWidget(self.text, 1)
        self.open_button = QPushButton('Open source article')
        self.open_button.setAccessibleName('Open source article')
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_source)
        reader_layout.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.link_status = QLabel('')
        self.link_status.setWordWrap(True)
        self.link_status.setAccessibleName('Link status')
        reader_layout.addWidget(self.link_status)
        self.splitter.addWidget(self.list)
        self.splitter.addWidget(reader)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([240, 650])
        layout.addWidget(self.splitter, 1)
        self.empty_text = ('Create a preview from the Dashboard while Dev mode is enabled.' if preview else
                           'No published articles yet. Leave the Discord webhook blank and choose Collect new on the Dashboard. Results stay on this PC.')
        self.text.setPlainText(self.empty_text)

    def refresh(self):
        paths = []
        for path in self.folder.glob('*.json'):
            try:
                paths.append((path, path.stat().st_mtime_ns))
            except OSError:
                continue
        stamp = tuple(sorted((str(p), time) for p, time in paths))
        if stamp == self.fingerprint:
            return
        self.fingerprint = stamp
        self.records = []
        for path, time in sorted(paths, key=lambda item: (-item[1], str(item[0]))):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(report, dict) or not isinstance(report.get('title'), str):
                    continue
                self.records.append((path, time, report))
            except (OSError, ValueError):
                continue
        self.filter()

    def filter(self, *_):
        selected = self.current_path
        query = self.search.text().casefold().strip()
        self.list.blockSignals(True)
        self.list.clear()
        selection = 0
        for record in self.records:
            path, time, report = record
            title, source = report['title'], report.get('source', 'Unknown')
            if not scopes.report_matches(report, self.filters):
                continue
            if query and query not in f'{title} {source}'.casefold():
                continue
            item = QListWidgetItem(f'{source}\n{title}')
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.list.addItem(item)
            if path == selected:
                selection = self.list.count() - 1
        self.list.blockSignals(False)
        count = self.list.count()
        self.count.setText(f'{count} article' + ('' if count == 1 else 's'))
        if self.list.count():
            self.list.setCurrentRow(selection)
        else:
            self.current_path = self.current_report = self.current_stamp = None
            self.open_button.setEnabled(False)
            self.text.setPlainText('No matching articles.' if query or any(self.filters.values()) else self.empty_text)
            self.link_status.clear()

    def set_scope(self, scope):
        self.set_filters({**self.filters, 'sector_scope': validate_scope(scope)})

    def set_filters(self, selected):
        self.filters = scopes.selection(selected)
        self.sector_scope = self.filters['sector_scope']
        self.filter()

    def show_selected(self, *_):
        selected = self.list.currentItem()
        if not selected:
            return
        path, stamp, report = selected.data(Qt.ItemDataRole.UserRole)
        if (path, stamp) == (self.current_path, self.current_stamp):
            return  # Do not reset reading position when another article arrives.
        self.current_path, self.current_stamp, self.current_report = path, stamp, report
        self.link_status.clear()
        try:
            self.text.setHtml(article_html(report, self.preview))
        except (AttributeError, KeyError, TypeError, ValueError):
            self.text.setPlainText('This article could not be displayed.')
        self.open_button.setEnabled(self.source_url() is not None)

    def update_link_colors(self, color):
        # Qt stores the current link color when parsing HTML. Update its anchor
        # formats after theme changes without losing selection or scroll position.
        document = self.text.document()
        ranges = []
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    ranges.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        style = QTextCharFormat()
        style.setForeground(color)
        cursor = QTextCursor(document)
        for position, length in ranges:
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(style)

    def source_url(self):
        return safe_article_url(self.current_report or {})

    def open_link(self, url):
        report = self.current_report or {}
        allowed = [self.source_url(), *(target for key in ('cves', 'attack_ids')
                                        for _, target in reference_links(report, key))]
        if url.toString() not in {QUrl(target).toString() for target in allowed if target}:
            return
        opened = QDesktopServices.openUrl(url)
        self.link_status.setText('Opened in your default browser.' if opened else
                                'Unable to open your browser. Right-click the link to copy its address.')

    def open_source(self):
        url = self.source_url()
        if url:
            self.open_link(QUrl(url))

    def set_compact(self, compact):
        orientation = Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            self.splitter.setSizes([140, 320] if compact else [240, 650])

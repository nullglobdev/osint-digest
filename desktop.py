"""OSINT Digest Windows desktop application and packaged worker entry point."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
import webbrowser

from desktop_settings import (APP_NAME, VERSION, DEFAULTS, data_directory,
                              initialize, load_settings, save_settings, atomic_json, resource_path)
from desktop_worker import ACTIONS, run_worker
from desktop_ai import PROVIDERS, KEY_ENV, PORTALS, list_models
from desktop_sources import make_source
from desktop_tray import Tray
from bot import error_label

TITLES = {'feeds': 'Checking publisher feeds', 'ai': 'Testing AI on a real article',
          'preview': 'Preparing batch preview', 'batch': 'Sending latest articles to Discord',
          'new': 'Checking for new articles', 'webhook': 'Checking Discord connection'}


class DigestApp:
    def __init__(self, window, root, discover_models=True):
        self.window, self.root = window, root
        initialize(root)
        self.process = None
        self.monitoring = False
        self.next_check = 0
        self.poll_id = None
        self.buttons = []
        self.settings_error = None
        try:
            self.settings = load_settings(root)
        except Exception:
            self.settings = deepcopy(DEFAULTS)
            self.settings_error = 'Saved settings could not be opened. Re-enter your connection details and save them.'
        self.sources = json.loads((root / 'sources.json').read_text(encoding='utf-8'))
        self.variables = {k: tk.StringVar(value=str(v)) for k, v in self.settings.items()
                          if k not in ('profiles', 'close_to_tray')}
        self.profiles = deepcopy(self.settings['profiles'])
        self.active_provider = self.settings['provider']
        self.events = queue.Queue()
        self.model_choices = {}
        self.model_inflight = set()
        self.last_lookup = None
        self.model_status = tk.StringVar(value='Refresh models after entering your API key, or type a model ID.')
        self.close_to_tray = tk.BooleanVar(value=self.settings['close_to_tray'])
        self.tray = None
        self.hide_pending = False
        self.quit_pending = False
        self.provider = tk.StringVar(value=next(k for k, v in PROVIDERS.items() if v == self.settings['provider']))
        self.status = tk.StringVar(value='Ready' if self.settings['webhook'] else 'Start with Connection to set up Discord and AI')
        self.monitor_status = tk.StringVar(value='Automatic checks are off')
        self.selected_count = tk.StringVar()
        self.source_vars = []
        self.report_paths = []
        self._build()
        self.refresh_reports()
        self._source_count()
        if not self.settings['webhook'] or self.settings_error:
            self.tabs.select(self.connection)
        if self.settings_error:
            self.window.after(150, lambda: messagebox.showwarning(APP_NAME, self.settings_error, parent=self.window))
        self.window.protocol('WM_DELETE_WINDOW', self.on_window_close)
        self.update_provider_fields()
        self.poll_id = self.window.after(250, self.poll)
        if discover_models:
            self.refresh_models(automatic=True)

    def _build(self):
        w = self.window
        w.title(APP_NAME)
        height = min(900, w.winfo_screenheight() - 80)
        w.geometry(f'1040x{height}')
        w.minsize(920, min(720, height))
        w.configure(bg='#f3f5f9')
        icon = resource_path('assets/app.ico')
        if icon.exists():
            w.iconbitmap(str(icon))
        style = ttk.Style(w)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#f3f5f9')
        style.configure('TLabel', background='#f3f5f9', foreground='#17253c')
        style.configure('Muted.TLabel', foreground='#526278')
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 17))
        style.configure('TLabelframe', background='#f3f5f9', bordercolor='#d3dce9')
        style.configure('TLabelframe.Label', background='#f3f5f9', foreground='#17253c', font=('Segoe UI Semibold', 11))
        style.configure('TButton', padding=(12, 8), background='#e4eaf3', foreground='#17253c')
        style.map('TButton', background=[('active', '#d4deed')])
        style.configure('Primary.TButton', background='#215ad6', foreground='white')
        style.map('Primary.TButton', background=[('active', '#1748b5'), ('disabled', '#d4deed')],
                  foreground=[('disabled', '#68778b')])
        style.configure('TCheckbutton', background='#f3f5f9')
        style.configure('TNotebook', background='#f3f5f9', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(22, 10))
        style.map('TNotebook.Tab', background=[('selected', '#ffffff')], foreground=[('selected', '#215ad6')])
        header = tk.Frame(w, bg='#14243e', padx=26, pady=20)
        header.pack(fill='x')
        tk.Label(header, text='OSINT DIGEST', fg='white', bg='#14243e',
                 font=('Segoe UI Semibold', 23)).pack(anchor='w')
        tk.Label(header, text='Threat intelligence, delivered to Discord.', fg='#bccde7',
                 bg='#14243e', font=('Segoe UI', 11)).pack(anchor='w', pady=(4, 0))
        footer = ttk.Frame(w, padding=(24, 8))
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, text=f'v{VERSION}', style='Muted.TLabel').pack(side='right')
        ttk.Button(footer, text='Exit', command=self.close).pack(side='right', padx=(8, 12))
        ttk.Button(footer, text='Run in background', command=self.hide_to_tray).pack(side='right', padx=8)
        ttk.Label(footer, textvariable=self.status, style='Muted.TLabel', wraplength=560).pack(side='left', fill='x', expand=True)
        self.progress = ttk.Progressbar(w, mode='indeterminate')
        self.progress.pack(side='bottom', fill='x', padx=24)
        self.tabs = ttk.Notebook(w)
        self.tabs.pack(fill='both', expand=True, padx=24, pady=(16, 8))
        self.dashboard = ttk.Frame(self.tabs, padding=18)
        self.connection = ttk.Frame(self.tabs, padding=22)
        self.source_tab = ttk.Frame(self.tabs, padding=22)
        self.reports = ttk.Frame(self.tabs, padding=18)
        for tab, title in ((self.dashboard, 'Dashboard'), (self.connection, 'Connection'),
                           (self.source_tab, 'Sources'), (self.reports, 'Previews')):
            self.tabs.add(tab, text=title)
        self._dashboard()
        self._connection()
        self._sources()
        self._reports()

    def button(self, parent, label, command, primary=False, **pack):
        b = ttk.Button(parent, text=label, command=command, style='Primary.TButton' if primary else 'TButton')
        b.pack(**pack)
        self.buttons.append(b)
        return b

    def _dashboard(self):
        ttk.Label(self.dashboard, text='Your research feed, in one place', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self.dashboard, text='Preview an AI summary, send a batch, or keep up with new articles.', style='Muted.TLabel').pack(anchor='w', pady=(5, 16))
        batch = ttk.LabelFrame(self.dashboard, text='Send the latest research', padding=14)
        batch.pack(fill='x')
        line = ttk.Frame(batch)
        line.pack(fill='x')
        ttk.Label(line, text='Articles per run').pack(side='left')
        ttk.Spinbox(line, from_=1, to=20, textvariable=self.variables['batch_size'], width=5).pack(side='left', padx=12)
        ttk.Label(line, textvariable=self.selected_count, style='Muted.TLabel').pack(side='left')
        actions = ttk.Frame(batch)
        actions.pack(fill='x', pady=(12, 8))
        self.button(actions, 'Send latest batch', lambda: self.start('batch'), primary=True, side='left', padx=(0, 8))
        self.button(actions, 'Preview batch', lambda: self.start('preview'), side='left', padx=(0, 8))
        self.button(actions, 'Test AI', lambda: self.start('ai'), side='left')
        ttk.Label(batch, text='One article per selected source. Latest batches can repeat articles already sent.',
                  style='Muted.TLabel').pack(anchor='w')
        auto = ttk.LabelFrame(self.dashboard, text='Keep up with new articles', padding=14)
        auto.pack(fill='x', pady=14)
        line = ttk.Frame(auto)
        line.pack(fill='x')
        self.button(line, 'Check & send new', lambda: self.start('new'), side='left', padx=(0, 16))
        ttk.Label(line, text='Check every').pack(side='left')
        self.interval_combo = ttk.Combobox(line, textvariable=self.variables['interval_minutes'],
                                         values=('15', '30', '60', '120', '180', '240', '300', '360'), width=5)
        self.interval_combo.pack(side='left', padx=8)
        ttk.Label(line, text='minutes').pack(side='left', padx=(0, 14))
        self.auto_button = ttk.Button(line, text='Start automatic checks', command=self.toggle_monitor)
        self.auto_button.pack(side='left')
        ttk.Label(auto, textvariable=self.monitor_status, style='Muted.TLabel').pack(anchor='w', pady=(10, 0))
        ttk.Label(auto, text='Checks continue in the tray while your PC is awake. The first check establishes a baseline.', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        ttk.Checkbutton(auto, text='Keep running in the system tray when I close the window',
                        variable=self.close_to_tray).pack(anchor='w', pady=(8, 0))
        line = ttk.Frame(self.dashboard)
        line.pack(fill='x', pady=(0, 8))
        ttk.Label(line, text='Activity', font=('Segoe UI Semibold', 11)).pack(side='left')
        self.button(line, 'Check feeds', lambda: self.start('feeds'), side='right')
        self.activity = ScrolledText(self.dashboard, height=8, wrap='word', font=('Consolas', 10),
                                    bg='white', fg='#243651', relief='flat', padx=12, pady=10)
        self.activity.pack(fill='both', expand=True)
        self.set_text(self.activity, 'Ready. Set up your connection, select sources, and preview your first batch.\n')

    def _connection(self):
        # Keep setup accessible on smaller screens and at larger Windows text sizes.
        canvas = tk.Canvas(self.connection, highlightthickness=0, bg='#f3f5f9')
        scrollbar = ttk.Scrollbar(self.connection, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas)
        inner = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(inner, width=event.width))
        ttk.Label(body, text='Connect your channel and AI', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Use your own Discord webhook and API key. Saved credentials are encrypted for your Windows account.',
                  style='Muted.TLabel', wraplength=820).pack(anchor='w', pady=(6, 18))
        form = ttk.Frame(body)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text='Discord webhook URL').grid(row=0, column=0, sticky='w', padx=(0, 18), pady=8)
        self.webhook_entry = ttk.Entry(form, textvariable=self.variables['webhook'], show='*')
        self.webhook_entry.grid(row=0, column=1, sticky='ew', pady=8)
        ttk.Label(form, text='Summary provider').grid(row=1, column=0, sticky='w', pady=8)
        provider = ttk.Combobox(form, values=list(PROVIDERS), textvariable=self.provider, state='readonly')
        provider.grid(row=1, column=1, sticky='ew', pady=8)
        provider.bind('<<ComboboxSelected>>', self.provider_changed)
        ttk.Label(form, text='AI API key').grid(row=2, column=0, sticky='w', pady=8)
        self.key_entry = ttk.Entry(form, textvariable=self.variables['api_key'], show='*')
        self.key_entry.grid(row=2, column=1, sticky='ew', pady=8)
        self.key_entry.bind('<FocusOut>', lambda event: self.refresh_models(automatic=True))
        ttk.Label(form, text='Model').grid(row=3, column=0, sticky='w', pady=8)
        model_row = ttk.Frame(form)
        model_row.grid(row=3, column=1, sticky='ew', pady=8)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.variables['model'])
        self.model_combo.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.model_refresh = ttk.Button(model_row, text='Refresh models', command=self.refresh_models)
        self.model_refresh.pack(side='right')
        ttk.Label(form, textvariable=self.model_status, wraplength=660, style='Muted.TLabel').grid(row=4, column=1, sticky='w')
        self.show_keys = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text='Show credentials', variable=self.show_keys, command=self.reveal).grid(row=5, column=1, sticky='w', pady=6)
        help_box = ttk.LabelFrame(body, text='Quick setup', padding=16)
        help_box.pack(fill='x', pady=18)
        ttk.Label(help_box, text='1. In Discord, open your channel settings > Integrations > Webhooks. Copy the webhook URL.\n'
                               '2. Choose your AI provider and enter its API key. Refresh models and choose a text model.\n'
                               '3. Save the connection, then use Test AI or Preview batch on the Dashboard.',
                  wraplength=820, justify='left').pack(anchor='w')
        ttk.Label(help_box, text='Cloud AI uses your provider account and may incur charges. Keys and model choices are saved separately for each provider.\n'
                               'Publisher excerpts need no AI key. Ollama lists models installed on this PC.',
                  style='Muted.TLabel', wraplength=820).pack(anchor='w', pady=(12, 0))
        row = ttk.Frame(body)
        row.pack(fill='x')
        self.button(row, 'Save connection', self.save, primary=True, side='left', padx=(0, 8))
        self.button(row, 'Test Discord connection', lambda: self.start('webhook'), side='left', padx=(0, 8))
        self.button(row, 'Import connection from .env', self.import_env, side='left')
        row = ttk.Frame(body)
        row.pack(fill='x', pady=12)
        self.portal_button = ttk.Button(row, text='Open provider portal', command=self.open_provider_portal)
        self.portal_button.pack(side='left', padx=(0, 8))
        self.button(row, 'Open app data folder', lambda: os.startfile(str(self.root)), side='left')

    def _sources(self):
        ttk.Label(self.source_tab, text='Choose your publishers', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self.source_tab, text='Batches use the first N selected sources in the order below. New-article checks use all selected sources.',
                  style='Muted.TLabel', wraplength=820).pack(anchor='w', pady=(6, 16))
        listing = ttk.Frame(self.source_tab)
        listing.pack(fill='both', expand=True)
        self.source_list = ttk.Treeview(listing, columns=('enabled', 'name', 'feed'), show='headings', selectmode='browse', height=10)
        for column, title, width in (('enabled', 'Use', 60), ('name', 'Publisher', 160), ('feed', 'RSS / Atom feed', 570)):
            self.source_list.heading(column, text=title)
            self.source_list.column(column, width=width, stretch=column == 'feed')
        scrollbar = ttk.Scrollbar(listing, orient='vertical', command=self.source_list.yview)
        self.source_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.source_list.pack(fill='both', expand=True)
        self.source_list.bind('<Double-1>', lambda event: self.toggle_source())
        self.rebuild_sources()
        row = ttk.Frame(self.source_tab)
        row.pack(fill='x', pady=12)
        for label, command in (('Add source', self.source_editor), ('Edit', lambda: self.source_editor(edit=True)),
                               ('Enable / disable', self.toggle_source), ('Remove', self.remove_source),
                               ('Move up', lambda: self.move_source(-1)), ('Move down', lambda: self.move_source(1))):
            self.button(row, label, command, side='left', padx=(0, 6))
        self.button(self.source_tab, 'Save sources', self.save, primary=True, anchor='w', pady=(0, 10))
        ttk.Label(self.source_tab, text='Disabling a source keeps its delivery history and queued articles for when you enable it again.',
                  style='Muted.TLabel', wraplength=820).pack(anchor='w')

    def _reports(self):
        row = ttk.Frame(self.reports)
        row.pack(fill='x')
        ttk.Label(row, text='Read before you send', style='Title.TLabel').pack(side='left')
        self.button(row, 'Refresh', self.refresh_reports, side='right')
        ttk.Label(self.reports, text='Local previews stay on this PC. Previewing does not send a Discord message.',
                  style='Muted.TLabel').pack(anchor='w', pady=(6, 10))
        self.report_list = ttk.Treeview(self.reports, columns=('source', 'title'), show='headings', height=5)
        self.report_list.heading('source', text='Source')
        self.report_list.heading('title', text='Article')
        self.report_list.column('source', width=130, stretch=False)
        self.report_list.column('title', width=650)
        self.report_list.pack(fill='x')
        self.report_list.bind('<<TreeviewSelect>>', self.show_report)
        self.report_text = ScrolledText(self.reports, wrap='word', font=('Segoe UI', 10), bg='white',
                                       relief='flat', padx=16, pady=12)
        self.report_text.pack(fill='both', expand=True, pady=(12, 0))
        self.set_text(self.report_text, 'Use Test AI or Preview batch to create your first preview.')

    @staticmethod
    def set_text(widget, value):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('end', value)
        widget.configure(state='disabled')

    def reveal(self):
        for entry in (self.webhook_entry, self.key_entry):
            entry.configure(show='' if self.show_keys.get() else '*')

    def provider_changed(self, event=None):
        self.remember_provider()
        self.active_provider = PROVIDERS[self.provider.get()]
        profile = self.profiles.get(self.active_provider, {})
        self.variables['api_key'].set(profile.get('api_key', ''))
        self.variables['model'].set(profile.get('model', ''))
        self.last_lookup = None
        self.show_keys.set(False)
        self.reveal()
        self.update_provider_fields()
        self.refresh_models(automatic=True)

    def remember_provider(self):
        self.profiles[self.active_provider] = {'api_key': self.variables['api_key'].get().strip(),
                                               'model': self.variables['model'].get().strip()}

    def update_provider_fields(self):
        provider = self.active_provider
        self.key_entry.configure(state='normal' if provider in KEY_ENV else 'disabled')
        self.model_combo.configure(state='disabled' if provider == 'none' else 'normal',
                                   values=self.model_choices.get(provider, []))
        self.model_refresh.configure(state='disabled' if provider == 'none' else 'normal')
        self.portal_button.configure(state='normal' if provider in PORTALS else 'disabled')
        self.model_status.set('No AI model or key needed.' if provider == 'none' else
                              'Refresh to list installed models; Ollama must be running.' if provider == 'ollama' else
                              'Enter this provider\'s API key, then refresh models. You can also type a model ID.')

    def open_provider_portal(self):
        if self.active_provider in PORTALS:
            webbrowser.open(PORTALS[self.active_provider])

    def refresh_models(self, automatic=False):
        provider, key = self.active_provider, self.variables['api_key'].get().strip()
        identity = (provider, key)
        if provider == 'none' or (provider in KEY_ENV and not key):
            return
        if identity in self.model_inflight or (automatic and identity == self.last_lookup):
            return
        self.last_lookup = identity
        self.model_inflight.add(identity)
        self.model_choices.pop(provider, None)
        self.model_combo.configure(values=[])
        self.model_status.set('Loading models from your provider...')
        def work():
            try:
                models, error = list_models(provider, key), None
            except Exception as exc:
                models, error = [], error_label(exc)
            self.events.put(('models', (identity, models, error)))
        threading.Thread(target=work, daemon=True).start()

    def rebuild_sources(self, selected=None):
        self.source_vars = [tk.BooleanVar(value=s.get('enabled', True)) for s in self.sources]
        self.source_list.delete(*self.source_list.get_children())
        for i, source in enumerate(self.sources):
            self.source_list.insert('', 'end', iid=str(i), values=(
                'Yes' if source.get('enabled', True) else 'No', source['name'], source['feed']))
        if selected is not None and self.sources:
            self.source_list.selection_set(str(selected))
            self.source_list.see(str(selected))
        self._source_count()

    def selected_source(self):
        selection = self.source_list.selection()
        return int(selection[0]) if selection else None

    def toggle_source(self):
        index = self.selected_source()
        if self.process or index is None:
            return
        self.sources[index]['enabled'] = not self.sources[index].get('enabled', True)
        self.rebuild_sources(index)
        self.status.set('Sources changed. Click Save sources to apply.')

    def move_source(self, offset):
        index = self.selected_source()
        if self.process or index is None or not 0 <= index + offset < len(self.sources):
            return
        self.sources[index], self.sources[index + offset] = self.sources[index + offset], self.sources[index]
        self.rebuild_sources(index + offset)
        self.status.set('Source order changed. Click Save sources to apply.')

    def remove_source(self):
        index = self.selected_source()
        if self.process or index is None:
            return
        # Removal affects the local source list only; delivery history remains on disk.
        self.sources.pop(index)
        self.rebuild_sources(min(index, len(self.sources) - 1) if self.sources else None)
        self.status.set('Source removed from this list. Click Save sources to apply.')

    def source_editor(self, edit=False):
        if self.process:
            return
        index = self.selected_source() if edit else None
        if edit and index is None:
            return
        source = self.sources[index] if edit else {'name': '', 'feed': '', 'hosts': [], 'enabled': True}
        dialog = tk.Toplevel(self.window)
        dialog.title('Edit source' if edit else 'Add RSS / Atom source')
        dialog.transient(self.window)
        dialog.resizable(True, False)
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill='both', expand=True)
        fields = {}
        for name, label, value in (('name', 'Publisher name', source['name']),
                                   ('feed', 'HTTPS feed URL', source['feed']),
                                   ('hosts', 'Article / redirect hosts', ', '.join(source['hosts']))):
            ttk.Label(body, text=label).pack(anchor='w', pady=(8, 4))
            fields[name] = tk.StringVar(value=value)
            entry = ttk.Entry(body, textvariable=fields[name], width=78)
            entry.pack(fill='x')
            if edit and name == 'name':
                entry.configure(state='readonly')
        ttk.Label(body, text='Enter an RSS or Atom feed, rather than a normal article page.\n'
                            'The feed host is included automatically. Add exact article or redirect domains,\n'
                            'separated by commas (for example: example.com, www.example.com).',
                  style='Muted.TLabel', wraplength=650).pack(anchor='w', pady=14)
        def accept():
            try:
                value = make_source(*(fields[k].get() for k in ('name', 'feed', 'hosts')),
                                    self.sources, editing=index, enabled=source.get('enabled', True))
            except ValueError as exc:
                messagebox.showerror('Check source', str(exc), parent=dialog)
                return
            if edit:
                self.sources[index] = value
            else:
                self.sources.append(value)
            self.rebuild_sources(index if edit else len(self.sources) - 1)
            self.status.set('Source updated. Save sources, then use Check feeds on the Dashboard.')
            dialog.destroy()
        ttk.Button(body, text='Apply to source list', command=accept, style='Primary.TButton').pack(side='left')
        ttk.Button(body, text='Cancel', command=dialog.destroy).pack(side='right')
        dialog.grab_set()

    def _source_count(self):
        self.selected_count.set(f'{sum(v.get() for v in self.source_vars)} sources selected')

    def save(self):
        if self.process:
            messagebox.showinfo(APP_NAME, 'Wait for the current task to finish before saving changes.', parent=self.window)
            return False
        try:
            if PROVIDERS[self.provider.get()] != self.active_provider:
                self.provider_changed()
            self.remember_provider()
            settings = {k: v.get().strip() for k, v in self.variables.items()}
            settings['provider'] = PROVIDERS[self.provider.get()]
            settings['batch_size'] = int(settings['batch_size'])
            settings['interval_minutes'] = int(settings['interval_minutes'])
            settings['profiles'] = deepcopy(self.profiles)
            settings['close_to_tray'] = self.close_to_tray.get()
            if not any(v.get() for v in self.source_vars):
                raise ValueError('Select at least one source.')
            save_settings(self.root, settings)
            for source, variable in zip(self.sources, self.source_vars):
                source['enabled'] = variable.get()
            atomic_json(self.root / 'sources.json', self.sources)
            self.settings = settings
            self.status.set('Settings saved')
            return True
        except ValueError as error:
            messagebox.showerror('Check settings', str(error), parent=self.window)
        except Exception:
            messagebox.showerror(APP_NAME, 'Unable to save settings. Check access to your app data folder.', parent=self.window)
        return False

    def import_env(self):
        path = filedialog.askopenfilename(parent=self.window, title='Choose your existing .env file',
                                         filetypes=[('Environment file', '.env'), ('All files', '*.*')])
        if not path:
            return
        try:
            values = {}
            for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    k, v = line.split('=', 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
            provider = values.get('AI_PROVIDER', 'gemini').lower()
            if provider not in PROVIDERS.values():
                raise ValueError('Unsupported provider')
            self.remember_provider()
            for item, env in KEY_ENV.items():
                if values.get(env):
                    self.profiles.setdefault(item, {'model': '', 'api_key': ''})['api_key'] = values[env]
            self.active_provider = provider
            self.provider.set(next(k for k, v in PROVIDERS.items() if v == provider))
            profile = self.profiles.get(provider, {})
            self.variables['api_key'].set(profile.get('api_key', ''))
            self.variables['model'].set(values.get('AI_MODEL', profile.get('model', '')))
            if values.get('DISCORD_WEBHOOK_URL'):
                self.variables['webhook'].set(values['DISCORD_WEBHOOK_URL'])
            self.last_lookup = None
            self.update_provider_fields()
            self.refresh_models(automatic=True)
            self.status.set('Connection imported. Click Save connection to store it.')
        except Exception:
            messagebox.showerror(APP_NAME, 'Unable to read that connection file.', parent=self.window)

    def start(self, action):
        if self.process or self.quit_pending or not self.save():
            return False
        settings = self.settings
        if action in ('batch', 'new', 'webhook') and not settings['webhook']:
            self.tabs.select(self.connection)
            messagebox.showinfo('Connect Discord', 'Add your channel webhook URL first.', parent=self.window)
            return False
        if action not in ('feeds', 'webhook') and settings['provider'] in KEY_ENV and not settings['api_key']:
            self.tabs.select(self.connection)
            messagebox.showinfo('Connect AI', 'Add this provider\'s AI API key or choose publisher excerpts.', parent=self.window)
            return False
        if action == 'ai' and settings['provider'] == 'none':
            messagebox.showinfo('Choose AI', 'Choose an AI provider in Connection to test AI.', parent=self.window)
            return False
        if action not in ('feeds', 'webhook') and settings['provider'] != 'none' and not settings['model']:
            self.tabs.select(self.connection)
            messagebox.showinfo('Choose a model', 'Refresh models and select a text model, or enter its model ID.', parent=self.window)
            return False
        if action in ('batch', 'preview') and settings['batch_size'] > sum(v.get() for v in self.source_vars):
            messagebox.showinfo('Batch size', 'Select more sources or lower the number of articles per run.', parent=self.window)
            return False
        try:
            (self.root / 'activity.log').write_text('', encoding='utf-8')
            cmd = ([sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve())])
            cmd += ['--data-dir', str(self.root), '--worker', action]
            environment = os.environ.copy()
            # A frozen worker must remain a child of the existing application bundle.
            self.process = subprocess.Popen(cmd, cwd=str(self.root), env=environment,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.current_action = action
            self.last_log = ''
            self.status.set(TITLES[action] + '...')
            self.set_text(self.activity, TITLES[action] + '...\n')
            self.tabs.select(self.dashboard)
            self.progress.start(12)
            for button in self.buttons:
                button.configure(state='disabled')
            return True
        except Exception:
            self.process = None
            messagebox.showerror(APP_NAME, 'Unable to start the task. Check access to the app folder.', parent=self.window)
            return False

    def toggle_monitor(self):
        if self.monitoring:
            self.monitoring = False
            self.auto_button.configure(text='Start automatic checks')
            self.monitor_status.set('Automatic checks are off; any current task will finish')
        elif not self.process and self.start('new'):
            self.monitoring = True
            self.next_check = time.time() + int(self.settings['interval_minutes']) * 60
            self.auto_button.configure(text='Stop automatic checks')

    def poll(self):
        if self.poll_id:
            self.window.after_cancel(self.poll_id)
            self.poll_id = None
        try:
            request = self.root / '.show-window'
            if request.exists():
                request.unlink()
                self.restore_window()
        except OSError:
            pass
        self.handle_events()
        if self.quit_pending and not self.process:
            self.close()
            return
        if self.process:
            try:
                log = (self.root / 'activity.log').read_text(encoding='utf-8', errors='replace')[-150000:]
                if log != self.last_log:
                    self.set_text(self.activity, log)
                    self.activity.see('end')
                    self.last_log = log
            except OSError:
                pass
            code = self.process.poll()
            if code is not None:
                # Capture the last output even if the worker exited between the read and poll.
                try:
                    self.set_text(self.activity, (self.root / 'activity.log').read_text(encoding='utf-8', errors='replace')[-150000:])
                    self.activity.see('end')
                except OSError:
                    pass
                action = self.current_action
                self.process = None
                self.progress.stop()
                for button in self.buttons:
                    button.configure(state='normal')
                self.status.set('Finished successfully' if code == 0 else 'Finished with errors. See Activity for details.')
                self.refresh_reports()
                if action in ('preview', 'ai') and code == 0:
                    self.tabs.select(self.reports)
                if self.monitoring:
                    self.next_check = time.time() + int(self.settings['interval_minutes']) * 60
        if self.quit_pending and not self.process:
            self.close()
            return
        if self.monitoring:
            self.monitor_status.set('Automatic checks enabled. Next check: ' + time.strftime('%I:%M %p', time.localtime(self.next_check)))
            if not self.process and time.time() >= self.next_check:
                if not self.start('new'):
                    self.toggle_monitor()
        self.poll_id = self.window.after(300, self.poll)

    def refresh_reports(self):
        if not hasattr(self, 'report_list'):
            return
        self.report_list.delete(*self.report_list.get_children())
        self.report_paths = sorted((self.root / 'preview').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        for i, path in enumerate(self.report_paths):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                self.report_list.insert('', 'end', iid=str(i), values=(report['source'], report['title']))
            except (OSError, ValueError, KeyError):
                continue
        children = self.report_list.get_children()
        if children:
            self.report_list.selection_set(children[0])
            self.show_report()

    def show_report(self, event=None):
        selected = self.report_list.selection()
        if not selected:
            return
        try:
            report = json.loads(self.report_paths[int(selected[0])].read_text(encoding='utf-8'))
            lines = [report['title'], report['url'], '', report['ai_status'], '']
            if report.get('analysis'):
                for key, title in (('summary', 'SUMMARY'), ('affected', 'AFFECTED'), ('actors', 'ACTORS / MALWARE'),
                                   ('techniques', 'TECHNIQUES'), ('actions', 'RECOMMENDATIONS')):
                    claims = report['analysis'].get(key, [])
                    lines += [title] + [c['text'] for c in claims] + ['']
            else:
                lines += ['PUBLISHER EXCERPT', report.get('publisher_excerpt', ''), '']
            lines += ['CVEs: ' + (', '.join(report.get('cves', [])) or 'None mentioned'),
                      'ATT&CK: ' + (', '.join(report.get('attack_ids', [])) or 'None mentioned'),
                      f"IOC candidates: {len(report.get('iocs', []))}"]
            self.set_text(self.report_text, '\n'.join(lines))
        except (OSError, ValueError, KeyError):
            self.set_text(self.report_text, 'This preview could not be opened. Run a new preview to replace it.')

    def handle_events(self):
        while not self.events.empty():
            event, payload = self.events.get_nowait()
            if event == 'models':
                identity, models, error = payload
                self.model_inflight.discard(identity)
                if identity != (self.active_provider, self.variables['api_key'].get().strip()):
                    continue
                if error:
                    self.model_status.set(f'Could not load models ({error}). Check your key / connection, then refresh.')
                else:
                    self.model_choices[self.active_provider] = models
                    self.model_combo.configure(values=models)
                    self.model_status.set(f'{len(models)} models loaded. Choose a text model and use Test AI.' if models else
                                          'No text models found. Check account access or enter a model ID.')
            elif event == 'tray_ready':
                if self.hide_pending:
                    self.window.withdraw()
                    self.hide_pending = False
            elif event == 'tray_error':
                self.hide_pending = False
                self.tray = None
                self.restore_window()
                self.status.set('System tray unavailable. Use the window\'s minimize button to keep running in the taskbar.')
            elif event == 'show':
                self.restore_window()
            elif event == 'stop_checks':
                if self.monitoring:
                    self.toggle_monitor()
            elif event == 'exit':
                self.quit_pending = True
                self.monitoring = False

    def hide_to_tray(self):
        self.status.set('Running in background. Open OSINT Digest from the system tray near the clock.')
        if self.tray and self.tray.ready:
            self.window.withdraw()
            return
        self.hide_pending = True
        if not self.tray:
            self.tray = Tray(self.events, resource_path('assets/app.ico'))
            self.tray.start()

    def restore_window(self):
        self.hide_pending = False
        self.window.deiconify()
        self.window.lift()

    def on_window_close(self):
        if self.close_to_tray.get():
            self.hide_to_tray()
        else:
            self.close()

    def close(self):
        self.monitoring = False
        if self.process:
            self.quit_pending = True
            self.auto_button.configure(state='disabled')
            self.monitor_status.set('Automatic checks stopped')
            self.status.set('Exiting after the current task finishes...')
            return
        if self.tray:
            self.tray.stop()
        if self.poll_id:
            self.window.after_cancel(self.poll_id)
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument('--data-dir', type=Path, default=data_directory(), help=argparse.SUPPRESS)
    parser.add_argument('--worker', choices=ACTIONS, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.data_dir = args.data_dir.resolve()
    if args.worker:
        return run_worker(args.data_dir, args.worker)
    initialize(args.data_dir)
    # One desktop controller per profile prevents competing workers/log writes.
    import msvcrt
    with (args.data_dir / '.desktop.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            root = tk.Tk()
            root.withdraw()
            (args.data_dir / '.show-window').touch()
            messagebox.showinfo(APP_NAME, 'OSINT Digest is already running. Its window will reopen; you can also use its system-tray icon.')
            root.destroy()
            return 1
        try:
            ctypes = __import__('ctypes')
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        window = tk.Tk()
        if args.smoke_test:
            window.withdraw()
        try:
            app = DigestApp(window, args.data_dir, discover_models=not args.smoke_test)
            if args.smoke_test:
                from desktop_settings import protect, unprotect
                assert unprotect(protect('local-smoke-check')) == 'local-smoke-check'
                window.update_idletasks()
                app.hide_to_tray()
                deadline = time.monotonic() + 8
                while not app.tray.ready and time.monotonic() < deadline:
                    time.sleep(0.02)
                    if not app.events.empty():
                        app.handle_events()
                        if app.tray is None:
                            raise RuntimeError('System tray unavailable')
                assert app.tray.ready, 'System tray startup timed out'
                app.handle_events()
                atomic_json(args.data_dir / 'smoke-test.json', {'version': VERSION, 'gui': 'ok', 'dpapi': 'ok', 'tray': 'ok',
                            'sources': len(app.sources), 'credentials_present': bool(app.settings['webhook'] or app.settings['api_key'])})
                app.close()
            else:
                window.mainloop()
            return 0
        except Exception as error:
            atomic_json(args.data_dir / 'startup-error.json', {'type': type(error).__name__})
            if not args.smoke_test:
                messagebox.showerror(APP_NAME, 'Unable to open the app. Check your app data folder or reinstall.', parent=window)
            window.destroy()
            return 1


if __name__ == '__main__':
    sys.exit(main())

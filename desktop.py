"""OSINT Digest desktop entry point. Workers do not load the GUI runtime."""
import argparse
from pathlib import Path
import sys

from desktop_settings import (APP_NAME, VERSION, data_directory, initialize, atomic_json,
                              protect, unprotect)
from desktop_worker import ACTIONS, run_worker


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
    import msvcrt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QAccessible
    from desktop_ui import DigestApp
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    with (args.data_dir / '.desktop.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            (args.data_dir / '.show-window').touch()
            return 0
        window = None
        try:
            window = DigestApp(args.data_dir, discover_models=not args.smoke_test)
            if args.smoke_test:
                assert unprotect(protect('local-smoke-check')) == 'local-smoke-check'
                qapp.processEvents()
                interface = QAccessible.queryAccessibleInterface(window.key_entry)
                assert interface.text(QAccessible.Text.Name) == 'AI API key'
                window.hide_to_tray()
                qapp.processEvents()
                assert window.tray.ready
                atomic_json(args.data_dir / 'smoke-test.json', {
                    'version': VERSION, 'gui': 'ok', 'dpapi': 'ok', 'tray': 'ok', 'accessibility': 'ok',
                    'sources': len(window.sources),
                    'credentials_present': bool(window.settings['webhook'] or window.settings['api_key'])})
                window.exit_app()
                return 0
            window.show()
            return qapp.exec()
        except Exception as error:
            atomic_json(args.data_dir / 'startup-error.json', {'type': type(error).__name__})
            if not args.smoke_test:
                QMessageBox.critical(window, APP_NAME, 'Unable to open the app. Check your app data folder or reinstall.')
            return 1


if __name__ == '__main__':
    sys.exit(main())

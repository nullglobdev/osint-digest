"""Qt tray integration, sharing the application's main event loop."""
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray:
    def __init__(self, parent, image_path, show, stop_checks, exit_app):
        self.icon = QSystemTrayIcon(QIcon(str(image_path)), parent)
        self.icon.setToolTip('OSINT Digest')
        self.menu = QMenu(parent)
        self.menu.addAction('Open OSINT Digest', show)
        self.menu.addAction('Stop automatic checks', stop_checks)
        self.menu.addSeparator()
        self.menu.addAction('Exit after current task', exit_app)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(lambda reason: show() if reason in (
            QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)

    @property
    def ready(self):
        return self.icon.isVisible()

    def start(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.icon.show()
        return True

    def stop(self):
        self.icon.hide()

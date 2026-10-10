"""Windows tray callbacks communicate with Tk only through a thread-safe queue."""
import threading


class Tray:
    def __init__(self, events, image_path):
        self.events, self.image_path = events, image_path
        self.icon = None
        self.ready = False
        self.stopping = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import pystray
            from PIL import Image
            with Image.open(self.image_path) as image:
                picture = image.copy()
            def send(event):
                return lambda icon, item: self.events.put((event, None))
            self.icon = pystray.Icon('OSINTDigest', picture, 'OSINT Digest', pystray.Menu(
                pystray.MenuItem('Open OSINT Digest', send('show'), default=True),
                pystray.MenuItem('Stop automatic checks', send('stop_checks')),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Exit (finish current task)', send('exit'))))
            def setup(icon):
                if self.stopping:
                    icon.stop()
                    return
                icon.visible = True
                self.ready = True
                self.events.put(('tray_ready', None))
            self.icon.run(setup)
        except Exception:
            self.events.put(('tray_error', None))
        finally:
            self.ready = False

    def stop(self):
        self.stopping = True
        if self.icon and self.ready:
            self.icon.stop()

"""Generate the application's original radar icon without third-party assets."""
import math
from pathlib import Path
import struct
import zlib


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


size = 256
rows = []
for y in range(size):
    row = bytearray(b'\x00')
    for x in range(size):
        dx, dy = x - 128, y - 128
        radius = math.hypot(dx, dy)
        color = (20, 36, 62, 255)
        if abs(radius - 42) < 2 or abs(radius - 78) < 2 or abs(radius - 106) < 2:
            color = (63, 103, 155, 255)
        if (abs(dx) < 1.5 or abs(dy) < 1.5) and radius < 106:
            color = (63, 103, 155, 255)
        if 0 < dx < 80 and abs(dy + dx) < 5:
            color = (65, 194, 222, 255)
        if math.hypot(dx - 52, dy + 53) < 10 or radius < 9:
            color = (135, 240, 225, 255)
        # Rounded background corners.
        if abs(dx) > 92 and abs(dy) > 92 and math.hypot(abs(dx) - 92, abs(dy) - 92) > 35:
            color = (0, 0, 0, 0)
        row.extend(color)
    rows.append(bytes(row))
png = b'\x89PNG\r\n\x1a\n'
png += chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b'')
target = Path(__file__).resolve().parent.parent / 'assets'
target.mkdir(exist_ok=True)
(target / 'app.ico').write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png)

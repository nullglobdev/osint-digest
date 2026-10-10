"""Build a portable headless source bundle from an explicit public-file allowlist."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

VERSION = '1.0.0'
FILES = ('Dockerfile', '.dockerignore', 'compose.yaml', 'bot.py', 'ai_endpoints.py',
         'desktop_ai.py', 'desktop_sources.py', 'server.py', 'server_settings.py',
         'server_setup.py', 'sources.json', 'CONTAINER.md', 'VALIDATION.md',
         'scripts/server.sh', 'scripts/test_container.py', 'test_bot.py', 'test_server.py')


def main():
    root = Path(__file__).resolve().parent.parent
    output = root / 'dist'
    output.mkdir(exist_ok=True)
    prefix = f'OSINTDigest-Server-{VERSION}'
    path = output / (prefix + '.tar.gz')
    with path.open('wb') as stream, gzip.GzipFile(fileobj=stream, filename='', mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name in (*FILES, 'README.md'):
                source = 'CONTAINER.md' if name == 'README.md' else name
                data = (root / source).read_bytes().replace(b'\r\n', b'\n')
                info = tarfile.TarInfo(prefix + '/' + name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / 'SERVER-SHA256SUMS.txt').write_text(f'{digest}  {path.name}\n', encoding='ascii')
    print(path)


if __name__ == '__main__':
    main()

"""Build a portable headless source bundle from an explicit public-file allowlist."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

VERSION = '1.6.0'
FILES = ('Dockerfile', '.dockerignore', 'compose.yaml', 'bot.py', 'server.py',
         'osint_digest/__init__.py', 'osint_digest/paths.py',
         'osint_digest/core/__init__.py', 'osint_digest/core/collector.py',
         'osint_digest/core/sectors.py', 'osint_digest/core/scopes.py', 'osint_digest/core/endpoints.py', 'osint_digest/core/providers.py', 'osint_digest/core/sources.py',
         'osint_digest/server/__init__.py', 'osint_digest/server/app.py',
         'osint_digest/server/delivery.py', 'osint_digest/server/settings.py', 'osint_digest/server/setup.py',
         'config/sources.json', 'docs/CONTAINER.md', 'docs/SCOPES.md', 'docs/VALIDATION.md',
         'scripts/server.sh', 'scripts/test_container.py', 'tests/__init__.py',
         'tests/test_bot.py', 'tests/test_server.py', 'tests/test_webhooks.py', 'tests/test_collection_window.py',
         'tests/test_sectors.py', 'tests/test_scopes.py',
         'tests/test_extraction.py', 'tests/benchmark_iocs.py',
         'tests/fixtures/extraction/README.md',
         'tests/fixtures/extraction/layouts.json', 'tests/fixtures/extraction/iocs.json',
         'tests/fixtures/extraction/microsoft.html', 'tests/fixtures/extraction/google.html',
         'tests/fixtures/extraction/huntress.html', 'tests/fixtures/extraction/proofpoint.html',
         'tests/fixtures/extraction/socradar.html', 'tests/fixtures/extraction/talos.html',
         'tests/fixtures/extraction/unit42.html', 'tests/fixtures/extraction/eset.html',
         'tests/fixtures/extraction/sentinellabs.html', 'tests/fixtures/extraction/securelist.html',
         'tests/fixtures/extraction/cisa.html',
         'docs/validation/ioc-benchmark-baseline.json', 'docs/validation/ioc-benchmark.json')


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=root / 'dist')
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prefix = f'OSINTDigest-Server-{VERSION}'
    path = output / (prefix + '.tar.gz')
    with path.open('wb') as stream, gzip.GzipFile(fileobj=stream, filename='', mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name in (*FILES, 'README.md'):
                source = 'docs/CONTAINER.md' if name == 'README.md' else name
                data = (root / source).read_bytes().replace(b'\r\n', b'\n')
                if name == 'README.md':
                    data = data.replace(b'](VALIDATION.md)', b'](docs/VALIDATION.md)')
                    data = data.replace(b'](SCOPES.md)', b'](docs/SCOPES.md)')
                info = tarfile.TarInfo(prefix + '/' + name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / 'SERVER-SHA256SUMS.txt').write_text(f'{digest}  {path.name}\n', encoding='ascii')
    print(path)


if __name__ == '__main__':
    main()

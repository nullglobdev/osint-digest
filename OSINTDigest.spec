# Explicit public-resource allowlist: never bundle .env, state, previews or logs.
from pathlib import Path
import sys
from importlib.metadata import distribution

root = Path(SPECPATH)
data = [(str(root / 'sources.json'), '.'), (str(root / 'assets/app.ico'), 'assets'),
        (str(root / 'DESKTOP.md'), '.'), (str(root / 'THIRD_PARTY_NOTICES.txt'), '.')]
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    data.append((str(python_license), 'licenses/python'))
for license_file in (Path(sys.base_prefix) / 'tcl').glob('*/license.terms'):
    data.append((str(license_file), 'licenses/tcl-tk/' + license_file.parent.name))
pyinstaller_dist = distribution('pyinstaller')
for file in pyinstaller_dist.files:
    if 'licenses' in file.parts and file.name in ('COPYING.txt', 'LICENSE', 'LICENSE.txt'):
        data.append((str(pyinstaller_dist.locate_file(file)), 'licenses/pyinstaller'))
a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['unittest', 'test', 'pydoc', 'doctest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OSINTDigest', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets/app.ico'), version=str(root / 'packaging/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='OSINTDigest')

"""Fix gsplat's pycolmap fork so it reads COLMAP binary models on Windows.

pycolmap (rmbrualla fork, used by gsplat's examples) unpacks COLMAP's 8-byte counts and
camera sizes with struct format 'L'. That is 8 bytes on Linux/macOS but 4 bytes on Windows,
so loading cameras.bin fails with "unpack requires a buffer of 4 bytes". Its text-format
reader is also broken (Python 2 `map`), so patching the binary reader is the reliable fix.

Run once after `pip install -r tools/requirements-gsplat-windows.txt`:
    .venv\\Scripts\\python tools\\patch_pycolmap_windows.py
Safe to run repeatedly.
"""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.find_spec("pycolmap")
if spec is None or not spec.submodule_search_locations:
    sys.exit("pycolmap is not installed in this Python environment.")

path = Path(list(spec.submodule_search_locations)[0]) / "scene_manager.py"
source = path.read_text(encoding="utf-8")
patched = source.replace("'IiLL'", "'IiQQ'").replace("struct.unpack('L',", "struct.unpack('Q',") \
                .replace("struct.pack('L',", "struct.pack('Q',")

if patched == source:
    print(f"already patched: {path}")
else:
    path.write_text(patched, encoding="utf-8")
    print(f"patched: {path}")

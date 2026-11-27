"""Windows: refuse load-time or delay-load imports that must not ship.

Usage: python check_imports.py <wheel>     (needs pefile)

Only the extension module may import vcruntime140.dll, which CPython ships.
"""

import pathlib
import re
import sys
import tempfile
import zipfile

import pefile

BAD = re.compile(r"x265|x264|msvcp140|vcruntime140|libgcc|libstdc|winpthread", re.I)


def main() -> None:
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(sys.argv[1]) as wheel:
            wheel.extractall(tmp)
        for path in sorted(pathlib.Path(tmp).rglob("*")):
            if path.suffix not in (".dll", ".pyd"):
                continue
            pe = pefile.PE(str(path))
            names = [
                entry.dll.decode()
                for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                for entry in getattr(pe, table, [])
            ]
            pe.close()
            print(f"  {path.name} -> {', '.join(names)}")
            failed += [
                f"{path.name} imports {n}"
                for n in names
                if BAD.search(n) and not (path.suffix == ".pyd" and n.lower() == "vcruntime140.dll")
            ]
    if failed:
        sys.exit("REFUSED: " + "; ".join(failed))


if __name__ == "__main__":
    main()

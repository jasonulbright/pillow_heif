"""Copy the committed tree to a build directory and apply the build-only edits.

Usage: python stage.py <destination> <libheif source dir> <libde265 source dir> <windows|linux>

The checkout is never edited, so an upstream merge meets only upstream text.
The edits are the local version label and the notice files that name what this
wheel carries.
"""

import io
import pathlib
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def pins() -> dict:
    rows = (ROOT / "spectra" / "pins.env").read_text(encoding="utf-8").splitlines()
    return dict(row.split("=", 1) for row in rows if row and not row.startswith("#"))


def main() -> None:
    dest, heif, de265 = (pathlib.Path(a) for a in sys.argv[1:4])
    platform = sys.argv[4]
    values = pins()
    # safe.directory: a CI container runs as another user than the one that checked out.
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT)]
    # The binding comes from the commit and the build rules from the working tree:
    # both must be the same text.
    dirty = subprocess.run([*git, "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip()
    if dirty:
        sys.exit(f"REFUSED: commit or remove these changes before a build: {dirty}")
    archive = subprocess.run([*git, "archive", "HEAD"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    version = dest / "pillow_heif" / "_version.py"
    text = version.read_text(encoding="utf-8")
    old = f'__version__ = "{values["BINDING_VERSION"]}"'
    if old not in text:
        sys.exit(f"REFUSED: {version.name} does not hold {old}; update spectra/pins.env with the upstream merge")
    version.write_text(text.replace(old, f'__version__ = "{values["WHEEL_VERSION"]}"'), encoding="utf-8")
    shutil.copyfile(ROOT / "spectra" / f"LICENSES_bundled-{platform}.txt", dest / "LICENSES_bundled.txt")
    shutil.copyfile(heif / "COPYING", dest / "COPYING.libheif")
    shutil.copyfile(de265 / "COPYING", dest / "COPYING.libde265")


if __name__ == "__main__":
    main()

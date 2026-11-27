"""Refuse a built wheel that carries an encoder or decodes the corpus differently.

Usage: python verify_wheel.py <wheel>     (run with that wheel and Pillow installed)
"""

import hashlib
import json
import pathlib
import re
import sys
import zipfile

from PIL import Image

import pillow_heif

HERE = pathlib.Path(__file__).resolve().parent
NATIVE = re.compile(r"\.(pyd|dll|so(\.[0-9.]+)?)$")
# File names that must not ship, and entry points that only an encoder library has.
FORBIDDEN_NAMES = re.compile(r"x265|x264|kvazaar|aom|rav1e|svtav1|msvcp140|vcruntime140|libgcc|libstdc|winpthread", re.I)
FORBIDDEN_SYMBOLS = (b"x265_encoder_encode", b"x265_encoder_open", b"x265_api_get", b"x264_encoder_encode", b"kvz_api_get")


def main() -> None:
    pins = dict(
        row.split("=", 1)
        for row in (HERE / "pins.env").read_text(encoding="utf-8").splitlines()
        if row and not row.startswith("#")
    )
    problems = []
    with zipfile.ZipFile(sys.argv[1]) as wheel:
        names = wheel.namelist()
        natives = [n for n in names if NATIVE.search(n)]
        for name in natives:
            if FORBIDDEN_NAMES.search(pathlib.PurePosixPath(name).name):
                problems.append(f"forbidden file in the wheel: {name}")
            data = wheel.read(name)
            problems += [f"{name} holds {s.decode()}" for s in FORBIDDEN_SYMBOLS if s in data]
        for need in ("COPYING.libheif", "COPYING.libde265"):
            if not any(n.endswith("/" + need) for n in names):
                problems.append(f"the wheel carries no {need}")
    print("native files:", *natives, sep="\n  ")
    libraries = [pathlib.PurePosixPath(n).name for n in natives if "_pillow_heif" not in n]
    for need in ("heif", "de265"):
        if not any(need in name for name in libraries):
            problems.append(f"lib{need} is not bundled as a separate library")

    info = pillow_heif.libheif_info()
    print(json.dumps(info))
    if info["libheif"] != pins["LIBHEIF_VERSION"]:
        problems.append(f"libheif reports {info['libheif']}")
    if set(info["decoders"]) != {"libde265"} or pins["LIBDE265_VERSION"] not in info["decoders"]["libde265"]:
        problems.append(f"decoders: {info['decoders']}")
    # `mask` is libheif's built-in stub, not a codec library.
    if not set(info["encoders"]) <= {"mask"} or info["HEIF"] != "":
        problems.append(f"an encoder is present: {info['encoders']} HEIF={info['HEIF']!r}")
    if pillow_heif.__version__ != pins["WHEEL_VERSION"]:
        problems.append(f"version {pillow_heif.__version__}")

    pillow_heif.register_heif_opener()
    expected = json.loads((HERE / "fingerprints.json").read_text(encoding="utf-8"))
    present = sorted(p.name for p in (HERE / "fixtures").glob("*.heic"))
    if present != sorted(expected):
        problems.append("the fixture set and fingerprints.json differ")
    for name, digest in sorted(expected.items()):
        with Image.open(HERE / "fixtures" / name) as im:
            im.load()
            got = hashlib.sha256(im.tobytes()).hexdigest()[:16]
        if got != digest:
            problems.append(f"{name} decodes to {got}, pinned {digest}")
    if problems:
        sys.exit("REFUSED:\n  " + "\n  ".join(problems))
    print(f"OK: decode-only, {len(expected)} fixtures match their pinned decodes")


if __name__ == "__main__":
    main()

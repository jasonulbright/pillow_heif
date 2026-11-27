"""The rules a built wheel must meet, as pure functions so that tests can break them.

Every rule is an allow-list: what the wheel may hold, import and report. A new
library, codec or import fails the build until someone changes the rule.
"""

import pathlib
import re

#: Content signatures of the binary formats a wheel could carry.
BINARY_MAGIC = (b"MZ", b"\x7fELF", b"!<arch>\n", b"\xcf\xfa\xed\xfe")

#: The only binaries a wheel may hold: exactly one match for each pattern.
NATIVE_FILES = {
    "windows": (
        r"_pillow_heif\.cp\d+-win_amd64\.pyd",
        r"heif-[0-9a-f]{32}\.dll",
        r"libde265-[0-9a-f]{32}\.dll",
    ),
    "linux": (
        r"_pillow_heif\.cpython-\d+-x86_64-linux-gnu\.so",
        r"libheif-[0-9a-f]{8}\.so(\.\d+)*",
        r"libde265-[0-9a-f]{8}\.so(\.\d+)*",
    ),
}

#: Entry points that only an encoder library has.
FORBIDDEN_SYMBOLS = (b"x265_encoder_encode", b"x265_encoder_open", b"x265_api_get", b"x264_encoder_encode", b"kvz_api_get")

# kind of the importing file -> patterns of what it may load.
WINDOWS_IMPORTS = {
    "extension": (r"kernel32\.dll", r"vcruntime140\.dll", r"api-ms-win-crt-[a-z0-9-]+\.dll", r"python3\d+\.dll",
                  r"heif-[0-9a-f]{32}\.dll"),
    "libheif": (r"kernel32\.dll", r"libde265-[0-9a-f]{32}\.dll"),
    "libde265": (r"kernel32\.dll",),
}
_LINUX_BASE = (r"libc\.so\.6", r"libm\.so\.6", r"libpthread\.so\.0", r"libdl\.so\.2", r"librt\.so\.1",
               r"ld-linux-x86-64\.so\.2", r"libgcc_s\.so\.1")
LINUX_IMPORTS = {
    "extension": (*_LINUX_BASE, r"libheif-[0-9a-f]{8}\.so(\.\d+)*"),
    "libheif": (*_LINUX_BASE, r"libstdc\+\+\.so\.6", r"libde265-[0-9a-f]{8}\.so(\.\d+)*"),
    "libde265": (*_LINUX_BASE, r"libstdc\+\+\.so\.6"),
}


def kind_of(name: str) -> str:
    base = pathlib.PurePosixPath(name).name
    if base.startswith("_pillow_heif"):
        return "extension"
    return "libde265" if "de265" in base else "libheif" if "heif" in base else "unknown"


def check_files(platform: str, entries: dict) -> list:
    """`entries` maps every zip entry name to its bytes."""
    problems = []
    binaries = sorted(name for name, data in entries.items() if data.startswith(BINARY_MAGIC))
    unmatched = list(binaries)
    for pattern in NATIVE_FILES[platform]:
        found = [n for n in unmatched if re.fullmatch(pattern, pathlib.PurePosixPath(n).name)]
        if len(found) != 1:
            problems.append(f"expected exactly one binary matching {pattern}, found {found}")
        for name in found:
            unmatched.remove(name)
    problems += [f"a binary that must not ship: {name}" for name in unmatched]
    for name in binaries:
        problems += [f"{name} holds {s.decode()}" for s in FORBIDDEN_SYMBOLS if s in entries[name]]
    for need in ("COPYING.libheif", "COPYING.libde265"):
        if not any(name.endswith("/" + need) for name in entries):
            problems.append(f"the wheel carries no {need}")
    return problems


def check_imports(platform: str, name: str, imports: list) -> list:
    table = WINDOWS_IMPORTS if platform == "windows" else LINUX_IMPORTS
    flags = re.IGNORECASE if platform == "windows" else 0
    allowed = table.get(kind_of(name), ())
    return [
        f"{name} loads {item}, which is not on the allow-list"
        for item in imports
        if not any(re.fullmatch(pattern, item, flags) for pattern in allowed)
    ]


def check_library_report(info: dict, version: str, pins: dict) -> list:
    problems = []
    if info.get("libheif") != pins["LIBHEIF_VERSION"]:
        problems.append(f"libheif reports {info.get('libheif')}")
    decoders = info.get("decoders") or {}
    if set(decoders) != {"libde265"} or pins["LIBDE265_VERSION"] not in decoders.get("libde265", ""):
        problems.append(f"decoders: {decoders}")
    # `mask` is libheif's built-in stub, not a codec library.
    if set(info.get("encoders") or {}) - {"mask"} or info.get("HEIF") != "" or info.get("AVIF") != "":
        problems.append(f"an encoder is present: {info.get('encoders')} HEIF={info.get('HEIF')!r} AVIF={info.get('AVIF')!r}")
    if version != pins["WHEEL_VERSION"]:
        problems.append(f"version {version}")
    return problems


def check_decodes(expected: dict, actual: dict) -> list:
    if not expected:
        return ["fingerprints.json is empty"]
    problems = []
    if sorted(expected) != sorted(actual):
        problems.append("the fixture set and fingerprints.json differ")
    for name in sorted(set(expected) & set(actual)):
        if expected[name] != actual[name]:
            problems.append(f"{name} decodes to {actual[name]}, pinned {expected[name]}")
    return problems


def read_pins(path: pathlib.Path) -> dict:
    rows = path.read_text(encoding="utf-8").splitlines()
    return dict(row.split("=", 1) for row in rows if row and not row.startswith("#"))

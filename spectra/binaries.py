"""Read what each binary in a wheel loads, and which protections it was linked with.

Windows needs pefile. Linux needs readelf, which the manylinux image has.
"""

import pathlib
import re
import struct
import subprocess

# PE DllCharacteristics bits that every Windows binary must carry.
PE_FLAGS = {"high-entropy ASLR": 0x0020, "ASLR": 0x0040, "NX": 0x0100, "Control Flow Guard": 0x4000}
CET_DEBUG_TYPE = 20  # IMAGE_DEBUG_TYPE_EX_DLLCHARACTERISTICS
CET_COMPAT = 0x1


def inspect_pe(path: pathlib.Path):
    """(imports, missing protections)."""
    import pefile  # noqa: PLC0415

    pe = pefile.PE(str(path))
    try:
        imports = [
            entry.dll.decode()
            for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
            for entry in getattr(pe, table, [])
        ]
        flags = pe.OPTIONAL_HEADER.DllCharacteristics
        missing = [name for name, bit in PE_FLAGS.items() if not flags & bit]
        cet = False
        for entry in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []):
            if entry.struct.Type == CET_DEBUG_TYPE:
                raw = pe.__data__[entry.struct.PointerToRawData : entry.struct.PointerToRawData + 4]
                cet = bool(struct.unpack("<I", raw)[0] & CET_COMPAT)
        if not cet:
            missing.append("CET compatibility")
        return imports, missing
    finally:
        pe.close()


def _readelf(flag: str, path: pathlib.Path) -> str:
    return subprocess.run(["readelf", flag, "-W", str(path)], check=True, capture_output=True, text=True).stdout


def inspect_elf(path: pathlib.Path):
    """(imports, missing protections)."""
    dynamic = _readelf("-d", path)
    segments = _readelf("-l", path)
    imports = re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", dynamic)
    missing = []
    if "GNU_RELRO" not in segments:
        missing.append("RELRO")
    if not re.search(r"BIND_NOW|FLAGS_1\).*\bNOW\b", dynamic):
        missing.append("immediate binding")
    stack = [line for line in segments.splitlines() if "GNU_STACK" in line]
    if not stack or re.search(r"\sRWE\s", stack[0]):
        missing.append("non-executable stack")
    return imports, missing

"""Refuse a built wheel that breaks a rule in gates.py or decodes a fixture differently.

Usage: python verify_wheel.py <wheel> <windows|linux>

Run with that wheel and Pillow installed. Windows also needs pefile on
sys.path (pass its site-packages in SPECTRA_TOOLS).
"""

import json
import os
import pathlib
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if os.environ.get("SPECTRA_TOOLS"):
    sys.path.append(os.environ["SPECTRA_TOOLS"])

import binaries  # noqa: E402
import gates  # noqa: E402


def check_binaries(platform: str, entries: dict) -> list:
    problems = []
    inspect = binaries.inspect_pe if platform == "windows" else binaries.inspect_elf
    with tempfile.TemporaryDirectory() as folder:
        for name, data in entries.items():
            if not data.startswith(gates.BINARY_MAGIC):
                continue
            path = pathlib.Path(folder) / pathlib.PurePosixPath(name).name
            path.write_bytes(data)
            imports, missing = inspect(path)
            print(f"  {path.name} -> {', '.join(imports)}")
            problems += gates.check_imports(platform, name, imports)
            problems += [f"{name} was linked without {item}" for item in missing]
    return problems


def main() -> None:
    wheel_path, platform = sys.argv[1], sys.argv[2]
    pins = gates.read_pins(HERE / "pins.env")
    with zipfile.ZipFile(wheel_path) as wheel:
        entries = {info.filename: wheel.read(info) for info in wheel.infolist() if not info.is_dir()}
    problems = gates.check_files(platform, entries)
    problems += check_binaries(platform, entries)

    import pillow_heif  # noqa: PLC0415
    from fingerprint import fingerprint_all  # noqa: PLC0415

    info = pillow_heif.libheif_info()
    print(json.dumps(info))
    problems += gates.check_library_report(info, pillow_heif.__version__, pins)
    expected = json.loads((HERE / "fingerprints.json").read_text(encoding="utf-8"))
    problems += gates.check_decodes(expected, fingerprint_all(pillow_heif))
    if problems:
        sys.exit("REFUSED:\n  " + "\n  ".join(problems))
    print(f"OK: decode-only, hardened, {len(expected)} fixtures match their pinned decodes")


if __name__ == "__main__":
    main()

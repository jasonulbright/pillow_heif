"""Each rule in gates.py must refuse what it exists to refuse. Standard library only.

    python spectra/test_gates.py
"""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import binaries  # noqa: E402
import gates  # noqa: E402
import verify_wheel  # noqa: E402

HASH = "0" * 32
PE = b"MZ" + b"\0" * 16
GOOD_FILES = {
    "_pillow_heif.cp315-win_amd64.pyd": PE,
    f"p.data/platlib/heif-{HASH}.dll": PE,
    f"p.data/platlib/libde265-{HASH}.dll": PE,
    "p.dist-info/licenses/COPYING.libheif": b"text",
    "p.dist-info/licenses/COPYING.libde265": b"text",
}
PINS = {"LIBHEIF_VERSION": "1.2.3", "LIBDE265_VERSION": "4.5.6", "WHEEL_VERSION": "7+spectra.1"}
GOOD_INFO = {
    "libheif": "1.2.3", "HEIF": "", "AVIF": "", "encoders": {"mask": "mask"},
    "decoders": {"libde265": "libde265 HEVC decoder, version 4.5.6"},
}
DECODES = {"a.heic": {"primary_index": 0, "images": [{"pixels": "1"}, {"pixels": "2"}]}}


class Files(unittest.TestCase):
    def test_the_expected_wheel_passes(self):
        self.assertEqual(gates.check_files("windows", GOOD_FILES), [])

    def test_refuses(self):
        cases = {
            "an extra library": {"p.data/platlib/libsharpyuv-1.dll": PE},
            "an encoder library": {"p.data/platlib/libx265-1.dll": PE},
            "an upper-case extension": {"p.data/platlib/ZLIB.DLL": PE},
            "a binary with no extension": {"p.data/blob": b"\x7fELF..."},
            "a static library": {"p.data/x.lib": b"!<arch>\n..."},
            "a second libheif": {f"p.data/other/heif-{'1' * 32}.dll": PE},
        }
        for label, extra in cases.items():
            with self.subTest(label):
                self.assertTrue(gates.check_files("windows", {**GOOD_FILES, **extra}))

    def test_refuses_a_missing_part(self):
        for name in GOOD_FILES:
            with self.subTest(name):
                self.assertTrue(gates.check_files("windows", {k: v for k, v in GOOD_FILES.items() if k != name}))

    def test_refuses_an_encoder_entry_point_inside_an_allowed_file(self):
        files = {**GOOD_FILES, f"p.data/platlib/heif-{HASH}.dll": PE + b"x265_api_get_217"}
        self.assertTrue(gates.check_files("windows", files))


class Imports(unittest.TestCase):
    def test_allowed(self):
        self.assertEqual(gates.check_imports("windows", f"heif-{HASH}.dll", ["KERNEL32.dll", f"libde265-{HASH}.dll"]), [])
        self.assertEqual(gates.check_imports("linux", "libde265-0000abcd.so.0.2.3", ["libc.so.6", "libstdc++.so.6"]), [])

    def test_refused(self):
        for platform, name, item in (
            ("windows", f"heif-{HASH}.dll", "libx265-1.dll"),
            ("windows", f"heif-{HASH}.dll", "MSVCP140.dll"),
            ("windows", f"libde265-{HASH}.dll", "VCRUNTIME140.dll"),
            ("windows", "mystery.dll", "KERNEL32.dll"),
            ("linux", "libheif-0000abcd.so.1", "libx265.so.215"),
            ("linux", "libheif-0000abcd.so.1", "libz.so.1"),
            ("linux", "_pillow_heif.cpython-315-x86_64-linux-gnu.so", "libde265.so.0"),
        ):
            with self.subTest(item=item, name=name):
                self.assertTrue(gates.check_imports(platform, name, [item]))


class Report(unittest.TestCase):
    def test_good(self):
        self.assertEqual(gates.check_library_report(GOOD_INFO, "7+spectra.1", PINS), [])

    def test_refused(self):
        changes = {
            "an encoder": {"encoders": {"mask": "mask", "x265": "x265"}},
            "an HEIF encoder name": {"HEIF": "x265 HEVC encoder"},
            "a second decoder": {"decoders": {**GOOD_INFO["decoders"], "ffmpeg": "x"}},
            "no decoder": {"decoders": {}},
            "another libheif": {"libheif": "1.2.2"},
            "another libde265": {"decoders": {"libde265": "version 4.5.5"}},
        }
        for label, change in changes.items():
            with self.subTest(label):
                self.assertTrue(gates.check_library_report({**GOOD_INFO, **change}, "7+spectra.1", PINS))
        self.assertTrue(gates.check_library_report(GOOD_INFO, "7", PINS))


class Decodes(unittest.TestCase):
    def test_equal_passes(self):
        self.assertEqual(gates.check_decodes(DECODES, copy.deepcopy(DECODES)), [])

    def test_refuses_a_changed_second_image_and_a_lost_one(self):
        changed = copy.deepcopy(DECODES)
        changed["a.heic"]["images"][1]["pixels"] = "3"
        lost = copy.deepcopy(DECODES)
        del lost["a.heic"]["images"][1]
        self.assertTrue(gates.check_decodes(DECODES, changed))
        self.assertTrue(gates.check_decodes(DECODES, lost))

    def test_refuses_an_empty_or_different_set(self):
        self.assertTrue(gates.check_decodes({}, {}))
        self.assertTrue(gates.check_decodes(DECODES, {}))
        self.assertTrue(gates.check_decodes(DECODES, {**DECODES, "b.heic": {}}))


class Struct:
    def __init__(self, **fields):
        self.__dict__.update(fields)


def fake_pe(flags=0x4160, cet=1):
    debug = [] if cet is None else [Struct(struct=Struct(Type=20, PointerToRawData=0))]
    return Struct(OPTIONAL_HEADER=Struct(DllCharacteristics=flags), DIRECTORY_ENTRY_DEBUG=debug,
                  __data__=(cet or 0).to_bytes(4, "little"))


DYNAMIC = " 0x000000000000001e (FLAGS)  BIND_NOW\n"
SEGMENTS = "  GNU_STACK      0x000000 0x0 0x0 0x000000 0x000000 RW  0x10\n  GNU_RELRO      0x000000\n"


class Protections(unittest.TestCase):
    def test_complete_binaries_pass(self):
        self.assertEqual(binaries.pe_missing(fake_pe()), [])
        self.assertEqual(binaries.elf_missing(DYNAMIC, SEGMENTS), [])
        self.assertEqual(binaries.elf_missing(" (FLAGS_1)  Flags: NOW\n", SEGMENTS), [])

    def test_each_missing_pe_protection_is_named(self):
        for name, bit in binaries.PE_FLAGS.items():
            with self.subTest(name):
                self.assertEqual(binaries.pe_missing(fake_pe(flags=0x4160 & ~bit)), [name])
        for cet in (0, None):
            self.assertEqual(binaries.pe_missing(fake_pe(cet=cet)), ["CET compatibility"])

    def test_each_missing_elf_protection_is_named(self):
        self.assertEqual(binaries.elf_missing("", SEGMENTS), ["immediate binding"])
        self.assertEqual(binaries.elf_missing(DYNAMIC, SEGMENTS.replace("GNU_RELRO", "LOAD")), ["RELRO"])
        self.assertEqual(binaries.elf_missing(DYNAMIC, SEGMENTS.replace("RW  ", "RWE ")), ["non-executable stack"])
        self.assertEqual(binaries.elf_missing(DYNAMIC, "GNU_RELRO"), ["non-executable stack"])

    def test_the_wheel_check_reports_what_the_inspection_finds(self):
        entries = {f"p/heif-{HASH}.dll": PE, "p/readme.txt": b"text"}
        found = verify_wheel.check_binaries("windows", entries, inspect=lambda path: (["libx265.dll"], ["RELRO"]))
        self.assertEqual(len(found), 2)
        self.assertIn("libx265.dll", found[0])
        self.assertIn("without RELRO", found[1])


if __name__ == "__main__":
    unittest.main()

# Spectra decode-only build

This branch (`spectra-build`) builds `pillow_heif` with **no HEVC encoder**, for
[Spectra PDF](https://github.com/jasonulbright/Spectra-PDF). It replaces the
discontinued `pi-heif` distribution. The wheel keeps the name `pillow_heif`.

No C or Python source of the project is edited. Everything specific to this build
is in `spectra/` and `.github/workflows/spectra-wheels.yml`.

| | |
|---|---|
| Wheel version | `1.9.0+spectra.1` (a local label: these are not upstream's files) |
| Platforms | CPython 3.15, Windows x86-64 and manylinux_2_28 x86-64 |
| Libraries | libheif and libde265, built from the release archives pinned in `pins.env` |

## Build

```powershell
pwsh -File spectra\build-windows.ps1 -Python C:\Path\To\Python315\python.exe
```

```sh
docker run --rm -v "$PWD:/io" -e PYTAG=cp315-cp315 \
  "$(grep '^MANYLINUX_IMAGE=' spectra/pins.env | cut -d= -f2-)" bash /io/spectra/build-linux.sh
```

The wheel is written to `spectra-dist/`. A build starts by removing the older
wheel of its platform from that folder, and it refuses a working tree with
uncommitted changes.

## What a build refuses

`gates.py` holds the rules as allow-lists, and `test_gates.py` shows that each
rule refuses a bad input. Both build scripts run the tests first, and
`verify_wheel.py` applies the rules to the wheel:

- any binary other than the extension, libheif and libde265;
- an import (`DT_NEEDED` on Linux) that is not on the list for that file;
- a missing protection: ASLR, NX, Control Flow Guard and CET compatibility on
  Windows; RELRO, immediate binding and a non-executable stack on Linux;
- an encoder entry point, an encoder that libheif reports, a second decoder, or a
  version that differs from `pins.env`;
- a fixture that decodes differently from `fingerprints.json`: every image, its
  mode, size, pixels, bit depth, primary flag, thumbnail list, EXIF and ICC, and
  the high-bit-depth output of the 10-bit files. The values were written with
  pi-heif 1.4.0, the decoder Spectra PDF shipped before this build.

## Replace a library

libheif and libde265 are separate files in the installed package. The extension
and libheif load them by the exact names in the wheel, which carry a hash. Give a
replacement the same file name.

## A note for the application

libheif turns off its own resource limits when the environment variable
`LIBHEIF_SECURITY_LIMITS` is `off`. Remove that variable from the environment of
a process that decodes untrusted files.

## Update to a new upstream release

1. Merge the upstream release tag into a branch from `spectra-build`.
2. In `pins.env`, set the binding, wheel and library versions and the archive
   SHA-256 values. Take the library versions from upstream's
   `libheif/build_libs.py`.
3. Update the two `LICENSES_bundled-*.txt` files.
4. Build both platforms and open a pull request to `spectra-build`.

A changed fingerprint is a change in decoded pixels. Compare the pictures before
you change the value.

## A new Python version

Set the interpreter in the workflow, `PYTAG`, and the two Pillow rows in
`test-requirements-*.txt`.

Upstream's workflows (`test.yml`, `wheels.yml`, `close-stale.yml`) are removed
from this branch. When a merge from upstream brings them back as a conflict, keep
them removed.

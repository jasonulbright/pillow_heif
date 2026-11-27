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

The wheel is written to `spectra-dist/`. Both scripts build from the committed
tree (`git archive HEAD`), so commit a change before you build it.

## What a build refuses

`verify_wheel.py` (both platforms) and `check_imports.py` (Windows) stop the
build when the wheel carries an encoder library or an encoder entry point, when
libheif reports an encoder, when a library version differs from `pins.env`, or
when one of the 13 images in `fixtures/` decodes to different pixels than
`fingerprints.json` records.

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

Upstream's own workflows (`test.yml`, `wheels.yml`, `close-stale.yml`) are not
used on this branch.

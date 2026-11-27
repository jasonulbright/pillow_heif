#!/bin/bash
# Builds the decode-only pillow_heif wheel for Linux x86-64 (manylinux_2_28).
# Runs inside the manylinux image named by MANYLINUX_IMAGE in pins.env:
#
#   docker run --rm -v "$PWD:/io" -e PYTAG=cp315-cp315 "$MANYLINUX_IMAGE" bash /io/spectra/build-linux.sh
#
# x265 is never downloaded or compiled: libheif and libde265 are built here
# from their pinned release archives, and upstream's build_libs.py is not used.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SPECTRA="$ROOT/spectra"
set -a; . <(grep -v '^#' "$SPECTRA/pins.env"); set +a
PYTAG=${PYTAG:-cp315-cp315}
PY="/opt/python/$PYTAG/bin/python"
[ -x "$PY" ] || { echo "REFUSED: no $PY in this image"; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
PREFIX="$WORK/prefix"
mkdir -p "$WORK/downloads" "$WORK/src" "$PREFIX" "$ROOT/spectra-dist"

fetch() { # url sha256
    local file="$WORK/downloads/${1##*/}"
    curl --proto '=https' --tlsv1.2 -fsSL --retry 4 --retry-delay 10 -o "$file" "$1"
    echo "$2  $file" | sha256sum -c - >/dev/null
    tar -xzf "$file" -C "$WORK/src"
}
fetch "$LIBHEIF_URL" "$LIBHEIF_SHA256"
fetch "$LIBDE265_URL" "$LIBDE265_SHA256"
HEIF_SRC="$WORK/src/libheif-$LIBHEIF_VERSION"
DE265_SRC="$WORK/src/libde265-$LIBDE265_VERSION"

command -v cmake >/dev/null || { echo "REFUSED: no cmake in this image"; exit 1; }
common=(-DCMAKE_BUILD_TYPE=Release "-DCMAKE_INSTALL_PREFIX=$PREFIX" -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=ON)
mapfile -t de265_options < <(tr -d '\r' < "$SPECTRA/libde265-options.txt" | sed '/^$/d')
mapfile -t heif_options < <(tr -d '\r' < "$SPECTRA/libheif-options.txt" | sed '/^$/d')

cmake -S "$DE265_SRC" -B "$WORK/build-de265" "${common[@]}" "${de265_options[@]}"
cmake --build "$WORK/build-de265" -j "$(nproc)"
cmake --install "$WORK/build-de265"
cmake -S "$HEIF_SRC" -B "$WORK/build-heif" "${common[@]}" "-DCMAKE_PREFIX_PATH=$PREFIX" "${heif_options[@]}"
if grep -E '^X265_LIBRARY:[^=]*=' "$WORK/build-heif/CMakeCache.txt" | grep -qv NOTFOUND; then
    echo "REFUSED: libheif configure found x265"; exit 1
fi
cmake --build "$WORK/build-heif" -j "$(nproc)"
cmake --install "$WORK/build-heif"

"$PY" -m venv "$WORK/venv-build"
"$WORK/venv-build/bin/python" -m pip install --disable-pip-version-check --require-hashes --no-deps \
    -r "$SPECTRA/build-requirements-linux.txt"
"$WORK/venv-build/bin/python" "$SPECTRA/stage.py" "$WORK/binding" "$HEIF_SRC" "$DE265_SRC" linux
CPATH="$PREFIX/include" LIBRARY_PATH="$PREFIX/lib" LIBHEIF_ROOT="$PREFIX" PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" \
    "$WORK/venv-build/bin/python" -m pip wheel --disable-pip-version-check --no-build-isolation --no-deps --no-index \
    -w "$WORK/unrepaired" "$WORK/binding"
LD_LIBRARY_PATH="$PREFIX/lib" auditwheel repair --plat manylinux_2_28_x86_64 -w "$WORK/dist" "$WORK"/unrepaired/*.whl
wheel=$(ls "$WORK"/dist/*.whl)

"$PY" -m venv "$WORK/venv-test"
"$WORK/venv-test/bin/python" -m pip install --disable-pip-version-check --require-hashes --only-binary :all: --no-deps \
    -r "$SPECTRA/test-requirements-linux.txt"
"$WORK/venv-test/bin/python" -m pip install --disable-pip-version-check --no-index --no-deps "$wheel"
"$WORK/venv-test/bin/python" -I "$SPECTRA/verify_wheel.py" "$wheel"

cp "$wheel" "$ROOT/spectra-dist/"
(cd "$ROOT/spectra-dist" && sha256sum "$(basename "$wheel")")

"""What the decoder returns for each fixture: every image, not only the primary one.

`fingerprints.json` was written by this module run against the decoder that
Spectra PDF shipped before this build (pi-heif 1.4.0):

    python fingerprint.py pi_heif > fingerprints.json
"""

import hashlib
import importlib
import json
import pathlib
import sys

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _digest(data) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()[:16] if data else ""


def fingerprint(module, path: pathlib.Path) -> dict:
    heif = module.open_heif(path)
    images = []
    for image in heif:
        picture = image.to_pillow()
        images.append({
            "mode": picture.mode,
            "size": list(picture.size),
            "pixels": _digest(picture.tobytes()),
            "bit_depth": image.info.get("bit_depth"),
            "primary": bool(image.info.get("primary")),
            "thumbnails": list(image.info.get("thumbnails") or []),
            "exif": _digest(image.info.get("exif")),
            "icc": _digest(image.info.get("icc_profile")),
        })
    result = {"primary_index": heif.primary_index, "images": images}
    if any((image["bit_depth"] or 8) > 8 for image in images):
        wide = module.open_heif(path, convert_hdr_to_8bit=False)
        result["high_bit_depth"] = [
            {"mode": image.mode, "size": list(image.size), "pixels": _digest(image.data)} for image in wide
        ]
    return result


def fingerprint_all(module, folder: pathlib.Path = FIXTURES) -> dict:
    return {path.name: fingerprint(module, path) for path in sorted(folder.glob("*.heic"))}


if __name__ == "__main__":
    print(json.dumps(fingerprint_all(importlib.import_module(sys.argv[1])), indent=1, sort_keys=True))

"""Generate Rook-owned synthetic framing fixtures; Pillow is developer tooling only.

Run without arguments for the small checked-in corpus. --include-noise additionally
creates a deterministic large fixture locally for real PNG-to-JPEG qualification;
that generated stress image is not part of the shipped FFmpeg payload.
"""
from pathlib import Path
import hashlib
import json
import random
import struct
import sys
import zlib

from PIL import Image, ImageDraw, ImageOps, __version__ as pillow_version

ROOT = Path(__file__).resolve().parent

def marked(width, height):
    image = Image.new("RGB", (width, height), (180, 180, 180))
    if min(width, height) < 4:
        return image
    draw = ImageDraw.Draw(image)
    edge = max(2, min(width, height) // 16)
    draw.rectangle((0, 0, width - 1, edge - 1), fill=(240, 20, 20))
    draw.rectangle((0, height - edge, width - 1, height - 1), fill=(20, 240, 20))
    draw.rectangle((0, edge, edge - 1, height - edge - 1), fill=(20, 20, 240))
    draw.rectangle((width - edge, edge, width - 1, height - edge - 1), fill=(240, 220, 20))
    draw.rectangle((width//2-edge, height//2-edge, width//2+edge, height//2+edge), fill=(100, 20, 180))
    return image

def png_chunks(data):
    position = 8
    while position < len(data):
        size = struct.unpack_from(">I", data, position)[0]
        yield data[position+4:position+8], data[position+8:position+8+size]
        position += 12 + size

def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

def write_png(name, chunks):
    (ROOT/name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunk(kind, data) for kind, data in chunks))

base = marked(1166, 912)
base.save(ROOT/"rgb-1166x912.png")
base.save(ROOT/"rgb-1166x912.jpg", quality=95, subsampling=0)
base.save(ROOT/"rgb-1166x912-lossless.webp", lossless=True)
base.save(ROOT/"rgb-1166x912-lossy.webp", quality=90)
for name, size in [("portrait.png", (720, 1280)), ("square.png", (912, 912)),
                   ("matching.png", (1280, 720)), ("odd-119x73.png", (119, 73)),
                   ("extreme-16384x720.png", (16384, 720)), ("thin.png", (16384, 1))]:
    marked(*size).save(ROOT/name)

alpha = Image.new("RGBA", (128, 96), (240, 40, 20, 128))
ImageDraw.Draw(alpha).rectangle((0, 0, 31, 95), fill=(240, 40, 20, 0))
alpha.save(ROOT/"alpha.png")
alpha.save(ROOT/"alpha.webp", lossless=True)
raw16 = b"".join(struct.pack("<H", (x*511 + y*73) % 65536) for y in range(96) for x in range(128))
Image.frombytes("I;16", (128, 96), raw16).save(ROOT/"depth16.png")
palette = Image.new("P", (128, 96))
palette.putpalette([value for i in range(256) for value in (i, (i*3)%256, (i*7)%256)])
palette.putdata([(x//8+y//8) % 256 for y in range(96) for x in range(128)])
palette.save(ROOT/"palette.png", transparency=0)

orientation_source = marked(120, 80)
for orientation in range(1, 9):
    exif = Image.Exif()
    exif[274] = orientation
    file = ROOT/f"orientation-{orientation}.jpg"
    orientation_source.save(file, quality=95, subsampling=0, exif=exif)
    with Image.open(file) as encoded:
        ImageOps.exif_transpose(encoded).save(ROOT/f"orientation-{orientation}-oracle.png")
exif = Image.Exif()
exif[274] = 6
orientation_source.save(ROOT/"orientation-6.png", exif=exif)
orientation_source.save(ROOT/"orientation-6.webp", lossless=True, exif=exif)

frame1 = marked(128, 96).convert("RGBA")
frame2 = Image.new("RGBA", (128, 96), (10, 40, 240, 255))
frame1.save(ROOT/"animated.png", save_all=True, append_images=[frame2], duration=100, loop=0)
frame1.save(ROOT/"animated.webp", save_all=True, append_images=[frame2], duration=100, loop=0, lossless=True)

static_chunks = list(png_chunks((ROOT/"alpha.png").read_bytes()))
single = []
for kind, data in static_chunks:
    single.append((kind, data))
    if kind == b"IHDR":
        single.extend([(b"acTL", struct.pack(">II", 1, 0)),
                       (b"fcTL", struct.pack(">IIIIIHHBB", 0, 128, 96, 0, 0, 1, 10, 0, 0))])
write_png("declared-single.png", single)
bad = [(kind, data if kind != b"fcTL" else data[:4] + b"\0\0\0\0" + data[8:]) for kind, data in single]
write_png("corrupt-animation.png", bad)
# Zero-entry IFD whose next pointer points to itself.
cyclic_tiff = b"II\x2a\x00\x08\x00\x00\x00\x00\x00\x08\x00\x00\x00"
with_cycle = static_chunks[:1] + [(b"eXIf", cyclic_tiff)] + static_chunks[1:]
write_png("cyclic-exif.png", with_cycle)
corrupt = bytearray((ROOT/"alpha.png").read_bytes())
corrupt[-5] ^= 1
(ROOT/"corrupt-crc.png").write_bytes(corrupt)

webp = (ROOT/"animated.webp").read_bytes()
position, kept, seen = 12, [], False
while position < len(webp):
    size = struct.unpack_from("<I", webp, position+4)[0]
    encoded = webp[position:position+8+size+(size&1)]
    if webp[position:position+4] != b"ANMF" or not seen:
        kept.append(encoded)
    if webp[position:position+4] == b"ANMF":
        seen = True
    position += 8+size+(size&1)
payload = b"WEBP" + b"".join(kept)
(ROOT/"declared-single.webp").write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
broken = bytearray((ROOT/"alpha.webp").read_bytes())
struct.pack_into("<I", broken, 16, 0xffffffff)
(ROOT/"chunk-overflow.webp").write_bytes(broken)

if "--include-noise" in sys.argv:
    rng = random.Random(1729)
    noise = Image.frombytes("L", (3840, 2160), rng.randbytes(3840*2160))
    stress = ROOT.parents[3]/"artifacts/video-framing-fixtures/generated-noise-4k.png"
    stress.parent.mkdir(parents=True, exist_ok=True)
    noise.save(stress)
    print("Generated local stress image:", stress, stress.stat().st_size)

files = []
for path in sorted(ROOT.iterdir()):
    if path.suffix.lower() not in (".png", ".jpg", ".webp") or path.name.startswith("generated-"):
        continue
    files.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
manifest = {
    "schema_version": 1,
    "origin": "Original Rook synthetic fixtures, MIT; no third-party photographs.",
    "generator": {"script": "generate-fixtures.py", "pillow": pillow_version},
    "pixel_oracles": {
        "markers": {"top": [240,20,20], "bottom": [20,240,20], "left": [20,20,240], "right": [240,220,20], "center": [100,20,180]},
        "alpha": {"transparent": [0,0,0], "half_alpha": [120,20,10]},
        "orientation": "Pillow ImageOps.exif_transpose on the independently encoded JPEG; per-orientation oracle PNGs.",
        "ordinary_fit": {"canvas": [1920,1080], "scaled": [1380,1080], "offset": [270,0]},
        "ordinary_fill": {"canvas": [1920,1080], "scaled": [1920,1502], "offset": [0,211]}
    },
    "generated_stress_fixture": {"path": "artifacts/video-framing-fixtures/generated-noise-4k.png", "seed": 1729, "size": [3840,2160], "mode": "L", "command": "generate-fixtures.py --include-noise"},
    "files": files,
}
(ROOT/"manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(files)} small fixtures; total {sum(f['bytes'] for f in files):,} bytes.")

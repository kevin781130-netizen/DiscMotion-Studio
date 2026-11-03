#!/usr/bin/env bash
# Cloud-only build gate. No Docker and no GitHub Actions required.
set -Eeuo pipefail
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
export NUGET_XMLDOC_MODE=skip

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

echo "GATE_BEGIN: .NET 10 SDK install / isolated Zoetrope integration test"
curl -fsSL --retry 2 --connect-timeout 20 https://dot.net/v1/dotnet-install.sh -o "$TEMP/dotnet-install.sh"
bash "$TEMP/dotnet-install.sh" --channel 10.0 --install-dir "$TEMP/dotnet" --no-path
export DOTNET_ROOT="$TEMP/dotnet"
export PATH="$DOTNET_ROOT:$PATH"

dotnet --version
dotnet restore "$ROOT/tools/Zoetrope/Zoetrope.csproj" --disable-parallel
dotnet build "$ROOT/tools/Zoetrope/Zoetrope.csproj" -c Release --no-restore -warnaserror
dotnet run --project "$ROOT/tools/Zoetrope/Zoetrope.csproj" -c Release --no-build -- --selftest

mkdir -p "$TEMP/portraits"
python3 - "$TEMP/portraits" <<'PY'
import pathlib, struct, sys, zlib

directory = pathlib.Path(sys.argv[1])
def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
for frame in range(12):
    width, height = 24, 32
    pixels = bytes([frame * 20]) * width
    raw = b"".join(b"\x00" + pixels for _ in range(height))
    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(raw)) +
           chunk(b"IEND", b""))
    (directory / f"{frame:02}.png").write_bytes(png)
PY

dotnet run --project "$ROOT/tools/Zoetrope/Zoetrope.csproj" -c Release --no-build -- \
    render --frames "$TEMP/portraits" --out "$TEMP/zoetrope-output"

python3 - "$TEMP/zoetrope-output" <<'PY'
from pathlib import Path
import struct, sys
out = Path(sys.argv[1])
expected = {"disc.png", "preview.html"} | {f"frame_{i:02}.png" for i in range(12)}
actual = {p.name for p in out.iterdir()}
assert actual == expected, f"Output file mismatch: {actual ^ expected}"
for name, dims in [("disc.png", (2400, 2400))] + [(f"frame_{i:02}.png", (300, 450)) for i in range(12)]:
    data = (out / name).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), f"Missing PNG signature: {name}"
    assert struct.unpack(">II", data[16:24]) == dims, f"Wrong dimensions: {name}"
html = (out / "preview.html").read_text(encoding="utf-8")
assert "frame_00.png" in html and "disc.png" in html
print("zoetrope-render-integration: PASS (14 files, PNG headers, 12 stills, preview)")
PY

# Run the REAL DiscImageStudio CD engine on the generated 12-sector image.
# Only 4,500 sectors / 60 seconds are used here as an inexpensive smoke test.
# The 80-minute optical raster and actual CD-R visibility are NOT validated.
dotnet restore "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" --disable-parallel
dotnet build "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-restore -warnaserror
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-generate --input "$TEMP/zoetrope-output/disc.png" \
    --output "$TEMP/zoetrope-output/cd-zoetrope.wav" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --tone-dither 1 --tone-levels 2 --interleave true --cue true
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-preview-track --track "$TEMP/zoetrope-output/cd-zoetrope.wav" \
    --output "$TEMP/zoetrope-output/cd-readback.png" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --size 800 --byte-step 12 --deinterleave true
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-preview-warp --input "$TEMP/zoetrope-output/disc.png" \
    --output "$TEMP/zoetrope-output/cd-source-warp.png" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --actual-r0 24.5 --actual-r1 56.8 --size 800 --samples-per-sector 196 \
    --tone-dither 1 --tone-levels 2

python3 - "$TEMP/zoetrope-output" <<'PY'
from pathlib import Path
import json, struct, sys
p = Path(sys.argv[1])
wav = p / "cd-zoetrope.wav"
cue = p / "cd-zoetrope.cue"
sidecar = p / "cd-zoetrope.wav.json"
expected_bytes = 4500 * 2352
assert wav.stat().st_size == expected_bytes + 44, "CD WAV size is incorrect"
with wav.open("rb") as f:
    header = f.read(44)
    samples = f.read(16384)
assert header[0:4] == b"RIFF" and header[8:16] == b"WAVEfmt "
assert struct.unpack_from("<HHIIHH", header, 20) == (1,2,44100,176400,4,16), "Not CD-DA PCM"
assert header[36:40] == b"data" and struct.unpack_from("<I",header,40)[0] == expected_bytes
assert len(set(samples)) > 1, "Image payload appears constant"
assert 'FILE "cd-zoetrope.wav" WAVE' in cue.read_text(encoding="utf-8-sig")
assert "TRACK 01 AUDIO" in cue.read_text(encoding="utf-8-sig")
metadata = json.loads(sidecar.read_text(encoding="utf-8"))
assert metadata["format"] == "cd-da-track-v1" and metadata["sectors"] == 4500
assert metadata["interleaved"] is True and metadata["toneLevels"] == 2
for fn in ("cd-readback.png", "cd-source-warp.png"):
    data = (p / fn).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), f"Bad preview PNG: {fn}"
    assert struct.unpack(">II",data[16:24]) == (800, 800), f"Bad preview size: {fn}"
print("cd-image-pipeline: PASS (DiscImageStudio CD WAV+CUE+metadata+readback+warp)")
PY

# Aligned 12-byte sampling: each preview must see identical logical positions.
python3 "$ROOT/tools/Zoetrope/compare_cd_readback.py" \
    --source "$TEMP/zoetrope-output/disc.png" \
    --warp "$TEMP/zoetrope-output/cd-source-warp.png" \
    --readback "$TEMP/zoetrope-output/cd-readback.png" \
    --report "$TEMP/zoetrope-output/quality-report.json" \
    --diff "$TEMP/zoetrope-output/cd-diff.png"

# Portrait blink fixture: 12 changing eye poses, face/background held fixed.
python3 "$ROOT/tools/Zoetrope/generate_blink_fixture.py" --out "$TEMP/portrait-frames"
dotnet run --project "$ROOT/tools/Zoetrope/Zoetrope.csproj" -c Release --no-build -- \
    render --frames "$TEMP/portrait-frames" --out "$TEMP/blink-output"
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-generate --input "$TEMP/blink-output/disc.png" \
    --output "$TEMP/blink-output/blink-cd.wav" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --tone-dither 1 --tone-levels 2 --interleave true --cue true
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-preview-track --track "$TEMP/blink-output/blink-cd.wav" \
    --output "$TEMP/blink-output/cd-readback.png" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --size 800 --byte-step 12 --deinterleave true
dotnet run --project "$ROOT/src/DiscImageStudio.Cli/DiscImageStudio.Cli.csproj" -c Release --no-build -- \
    cd-preview-warp --input "$TEMP/blink-output/disc.png" \
    --output "$TEMP/blink-output/cd-source-warp.png" \
    --sectors 4500 --r0 24.5 --r1 56.8 --outer 57.5 \
    --actual-r0 24.5 --actual-r1 56.8 --size 800 --samples-per-sector 196 \
    --tone-dither 1 --tone-levels 2
python3 "$ROOT/tools/Zoetrope/check_blink_quality.py" \
    --frames "$TEMP/portrait-frames" \
    --warp "$TEMP/blink-output/cd-source-warp.png" \
    --readback "$TEMP/blink-output/cd-readback.png" \
    --report "$TEMP/blink-output/blink-quality-report.json"

publish="$ROOT/tools/Zoetrope/_render_public"
mkdir -p "$publish"
cp "$TEMP/zoetrope-output/"*.png "$publish/"
cp "$TEMP/zoetrope-output/preview.html" "$publish/index.html"
cp "$TEMP/zoetrope-output/cd-readback.png" "$publish/cd-readback.png"
cp "$TEMP/zoetrope-output/cd-source-warp.png" "$publish/cd-source-warp.png"
cp "$TEMP/zoetrope-output/quality-report.json" "$publish/quality-report.json"
cp "$TEMP/zoetrope-output/cd-diff.png" "$publish/cd-diff.png"
mkdir -p "$publish/blink"
cp "$TEMP/blink-output/"*.png "$publish/blink/"
cp "$TEMP/blink-output/"frame_*.png "$publish/blink/"
cp "$TEMP/blink-output/preview.html" "$publish/blink/index.html"
cp "$TEMP/blink-output/blink-quality-report.json" "$publish/blink/quality-report.json"
printf 'ZOETROPE_CD_GATE_PASS\nsource_branch=feature/zoetrope-animation-v1\ncd_smoke_sectors=4500\n' > "$publish/gate.txt"
echo "GATE_PASS: dotnet release compile + synthetic eye-motion CD readback quality test"

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

publish="$ROOT/tools/Zoetrope/_render_public"
mkdir -p "$publish"
cp "$TEMP/zoetrope-output/"*.png "$publish/"
cp "$TEMP/zoetrope-output/preview.html" "$publish/index.html"
printf 'ZOETROPE_GATE_PASS\nsource_branch=feature/zoetrope-animation-v1\n' > "$publish/gate.txt"
echo "GATE_PASS: dotnet release compile + selftest + 12-frame render integration"

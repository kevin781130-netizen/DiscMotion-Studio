#!/usr/bin/env python3
"""Measure encoded CD-image readback against a matched geometry projection.

The on-disc *appearance* is unverified. This is a purely digital comparison of
two outputs from the SAME upstream DiscImageStudio CD image encoder.
No third-party Python libraries are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import struct
import sys
import zlib

RING_MIN_MM = 25.5
RING_MAX_MM = 56.0
IMAGE_OUTER_MM = 57.5
N_SECTORS = 12
MIN_EXACT_AGREEMENT = 0.985
MIN_SECTOR_CORRELATION = 0.90


def read_gray_png(path: pathlib.Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Not a PNG: {path}")
    pos = 8
    width = height = depth = color = interlace = None
    chunks = []
    while pos + 12 <= len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        name = data[pos + 4 : pos + 8]
        start = pos + 8
        finish = start + length
        if finish + 4 > len(data):
            raise ValueError(f"Truncated PNG chunk in {path}")
        payload = data[start:finish]
        crc = struct.unpack_from(">I", data, finish)[0]
        if zlib.crc32(name + payload) & 0xFFFFFFFF != crc:
            raise ValueError(f"Bad PNG chunk CRC in {path}")
        pos = finish + 4
        if name == b"IHDR":
            if width is not None:
                raise ValueError("Duplicate IHDR")
            width, height, depth, color, compression, filter_method, interlace = struct.unpack(">IIBBBBB", payload)
            if depth != 8 or color not in (0, 2, 6) or compression or filter_method or interlace:
                raise ValueError("Only noninterlaced 8-bit Gray/RGB/RGBA PNG is supported")
            if not (1 <= width <= 2400 and 1 <= height <= 2400):
                raise ValueError("Unexpected PNG dimensions")
        elif name == b"IDAT":
            chunks.append(payload)
        elif name == b"IEND":
            break
    if width is None or not chunks:
        raise ValueError("Missing IHDR or IDAT")
    channels = {0: 1, 2: 3, 6: 4}[color]
    stride = width * channels
    raw = zlib.decompress(b"".join(chunks))
    if len(raw) != (stride + 1) * height:
        raise ValueError(f"Incorrect decoded PNG payload size: {path}")

    pixels = bytearray(width * height)
    previous = bytearray(stride)
    index = 0
    for y in range(height):
        kind = raw[index]
        index += 1
        row = bytearray(raw[index : index + stride])
        index += stride
        if kind == 1:  # Sub
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 255
        elif kind == 2:  # Up
            for i in range(stride):
                row[i] = (row[i] + previous[i]) & 255
        elif kind == 3:  # Average
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((left + previous[i]) >> 1)) & 255
        elif kind == 4:  # Paeth
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
                row[i] = (row[i] + predictor) & 255
        elif kind != 0:
            raise ValueError(f"Invalid PNG filter {kind} in {path}")
        if channels == 1:
            pixels[y * width : (y + 1) * width] = row
        else:
            for x in range(width):
                off = x * channels
                r, g, b = row[off : off + 3]
                if r != g or g != b:
                    raise ValueError(f"Preview PNG is not grayscale: {path}")
                pixels[y * width + x] = r
        previous = row
    return width, height, bytes(pixels)


def write_gray_png(path: pathlib.Path, width: int, height: int, pixels: bytes) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(
            ">I", zlib.crc32(kind + payload) & 0xFFFFFFFF
        )
    if len(pixels) != width * height:
        raise ValueError("PNG buffer length mismatch")
    rows = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def correlation(a: list[float], b: list[float]) -> float:
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((u - mean_a) * (v - mean_b) for u, v in zip(a, b))
    var_a = sum((u - mean_a) ** 2 for u in a)
    var_b = sum((v - mean_b) ** 2 for v in b)
    return cov / math.sqrt(var_a * var_b) if var_a and var_b else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantify digital CD readback image fidelity")
    parser.add_argument("--source", required=True, type=pathlib.Path)
    parser.add_argument("--warp", required=True, type=pathlib.Path)
    parser.add_argument("--readback", required=True, type=pathlib.Path)
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument("--diff", required=True, type=pathlib.Path)
    args = parser.parse_args()

    (sw, sh, source) = read_gray_png(args.source)
    (ww, wh, warp) = read_gray_png(args.warp)
    (rw, rh, readback) = read_gray_png(args.readback)
    if (sw, sh, ww, wh, rw, rh) != (2400, 2400, 800, 800, 800, 800):
        raise ValueError("Expected 2400² source and two 800² preview PNGs")

    delta_image = bytearray(ww * wh)
    ring_count = exact = total_difference = squared_difference = 0
    source_difference = source_squared_difference = 0
    source_vs_warp_difference = 0
    sums_src = [0] * N_SECTORS
    sums_warp = [0] * N_SECTORS
    sums_read = [0] * N_SECTORS
    counts = [0] * N_SECTORS
    # A pixel represents the same physical position at both output resolutions.
    # Do not compare unrelated source pixels by raw array index.
    for y in range(wh):
        dy = y - wh // 2
        for x in range(ww):
            pos = y * ww + x
            delta = abs(warp[pos] - readback[pos])
            delta_image[pos] = delta
            dx = x - ww // 2
            radius_mm = math.hypot(dx, dy) * IMAGE_OUTER_MM / (ww / 2)
            if not (RING_MIN_MM <= radius_mm <= RING_MAX_MM):
                continue
            angle = math.atan2(dx, -dy) % (2 * math.pi)
            sector_f = angle * N_SECTORS / (2 * math.pi)
            sector = int(sector_f)
            fraction = sector_f - sector
            # Ignore wedge gutters and sector transitions to compare uniform
            # luminance of the known numbered test pattern, not motion edges.
            if fraction < 0.06 or fraction > 0.94:
                continue
            sx = (x - 400) * 3 + 1200
            sy = (y - 400) * 3 + 1200
            if not (0 <= sx < 2400 and 0 <= sy < 2400):
                raise ValueError("Unexpected source-coordinate mapping")
            src_value = source[sy * 2400 + sx]
            ring_count += 1
            exact += delta == 0
            total_difference += delta
            squared_difference += delta * delta
            source_difference += abs(src_value - readback[pos])
            source_squared_difference += (src_value - readback[pos]) ** 2
            source_vs_warp_difference += abs(src_value - warp[pos])
            sums_src[sector] += src_value
            sums_warp[sector] += warp[pos]
            sums_read[sector] += readback[pos]
            counts[sector] += 1

    if ring_count < 10000 or not all(counts):
        raise ValueError("Ring region is empty or a frame sector is missing")
    source_means = [s / n for s, n in zip(sums_src, counts)]
    warp_means = [s / n for s, n in zip(sums_warp, counts)]
    read_means = [s / n for s, n in zip(sums_read, counts)]
    exact_fraction = exact / ring_count
    sector_r = correlation(warp_means, read_means)
    source_r = correlation(source_means, read_means)
    mae = total_difference / ring_count
    mse = squared_difference / ring_count
    psnr = float("inf") if mse == 0 else 10 * math.log10(255 * 255 / mse)
    failures = []
    if exact_fraction < MIN_EXACT_AGREEMENT:
        failures.append(f"warp_vs_readback_exact_rate_below_{MIN_EXACT_AGREEMENT}")
    if sector_r < MIN_SECTOR_CORRELATION:
        failures.append(f"sector_mean_correlation_below_{MIN_SECTOR_CORRELATION}")
    if max(read_means) - min(read_means) < 10:
        failures.append("readback_lacks_sector_luminance_contrast")

    report = {
        "gate": "PASS" if not failures else "FAIL",
        "scope": "offline 4500-sector synthetic 12-wedge CD-DA image; not physical-disc acceptance",
        "sampling": {
            "cd_sectors": 4500, "track_seconds": 60,
            "byte_step": 12, "warp_samples_per_sector": 196,
            "roi_radius_mm": [RING_MIN_MM, RING_MAX_MM],
            "sector_edge_exclusion_fraction": 0.06,
            "roi_pixels": ring_count,
        },
        "warp_vs_readback": {
            "exact_pixel_ratio": round(exact_fraction, 6),
            "mae_gray_levels": round(mae, 4),
            "rmse_gray_levels": round(math.sqrt(mse), 4),
            "psnr_db": round(psnr, 3) if math.isfinite(psnr) else None,
            "sector_mean_pearson_r": round(sector_r, 6),
        },
        "source_vs_readback": {
            "mae_gray_levels": round(source_difference / ring_count, 4),
            "rmse_gray_levels": round(math.sqrt(source_squared_difference / ring_count), 4),
            "sector_mean_pearson_r": round(source_r, 6),
        },
        "source_vs_warp": {
            "mae_gray_levels": round(source_vs_warp_difference / ring_count, 4),
        },
        "sector_means": {
            "source": [round(v, 2) for v in source_means],
            "projection": [round(v, 2) for v in warp_means],
            "readback": [round(v, 2) for v in read_means],
        },
        "inputs_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("source", args.source), ("projection", args.warp), ("readback", args.readback)
            )
        },
        "warnings": [
            "A 60-second synthetic image track is not a standard full-capacity CD-R physical geometry test.",
            "WAV contains encoded image pattern, not the artist's audio.",
            "Optical reflectivity, spinning strobe visibility and real CD burner compatibility remain unverified.",
            "The reference projection and readback reuse the same software geometry: agreement does not certify physical accuracy.",
        ],
        "failures": failures,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_gray_png(args.diff, ww, wh, delta_image)
    print(
        f"cd-fidelity: {report['gate']} | exact={exact_fraction:.3%} | "
        f"MAE={mae:.3f}/255 | sector-r={sector_r:.4f} | source-sector-r={source_r:.4f}"
    )
    if failures:
        print("QUALITY_GATE_FAILURES: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("cd-fidelity-report: PASS (quality-report.json, cd-diff.png)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

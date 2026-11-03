#!/usr/bin/env python3
"""Deterministic, *uncalibrated* optical-stress simulation of a CD image preview.

Low contrast, box blur, a localized specular highlight and spatial noise are
synthetic perturbations, NOT measurements of CD-R reflectance, LEDs or a camera.
A robust digital eye-motion signal is necessary, not sufficient, for a physical
zoetrope. This tool never changes the optical-disc encoder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from check_blink_quality import map_to_cd
from compare_cd_readback import correlation, read_gray_png, write_gray_png

N = 800
OPEN = (0, 1, 10, 11)
CLOSED = (5, 6)
# An 8/255 luminance swing and temporal Pearson r >= 0.85 are *test heuristics*
# for the synthetic signal, not psychophysical visibility thresholds.
GAP_THRESHOLD = 8.0
CORR_THRESHOLD = 0.85
CONTRASTS = (1.0, 0.75, 0.50, 0.35, 0.25, 0.15, 0.10, 0.05, 0.0)
BLUR_RADII = (0, 2, 4, 8)
GLARES = (0, 45, 100)
NOISE_AMPLITUDES = (0, 10)


def integral_image(pixels: bytes, w: int, h: int) -> list[int]:
    if len(pixels) != w * h:
        raise ValueError("Input pixels do not match image size")
    stride = w + 1
    result = [0] * ((h + 1) * stride)
    for y in range(h):
        row_sum = 0
        for x in range(w):
            row_sum += pixels[y * w + x]
            result[(y + 1) * stride + x + 1] = (
                result[y * stride + x + 1] + row_sum
            )
    return result


def blur_at(pixels: bytes, integral: list[int], x: int, y: int, radius: int) -> float:
    if radius == 0:
        return float(pixels[y * N + x])
    x0, x1 = max(0, x - radius), min(N - 1, x + radius)
    y0, y1 = max(0, y - radius), min(N - 1, y + radius)
    stride = N + 1
    total = (integral[(y1 + 1) * stride + x1 + 1]
             - integral[y0 * stride + x1 + 1]
             - integral[(y1 + 1) * stride + x0]
             + integral[y0 * stride + x0])
    return total / ((x1 + 1 - x0) * (y1 + 1 - y0))


def noise_unit(x: int, y: int) -> float:
    z = (x * 73856093) ^ (y * 19349663) ^ 0x9E3779B9
    z ^= z >> 16
    z = (z * 0x7FEB352D) & 0xFFFFFFFF
    z ^= z >> 15
    z = (z * 0x846CA68B) & 0xFFFFFFFF
    z ^= z >> 16
    return (z / 2147483647.5) - 1.0


def glare_field(x: int, y: int) -> float:
    # A fixed camera-space glint, not one that follows each frame.
    # Its offset deliberately introduces unequal illumination of wedges.
    return math.exp(-0.5 * (((x - 320) / 185) ** 2 + ((y - 285) / 87) ** 2))


def perturb(base: float, x: int, y: int,
            contrast: float, glare: float, noise: float) -> float:
    value = 165 + contrast * (base - 165)
    value += glare * glare_field(x, y)
    value += noise * noise_unit(x, y)
    return min(255.0, max(0.0, value))


def roi_positions() -> list[tuple[list[tuple[int, int]], list[tuple[int, int]]]]:
    result = []
    for frame in range(12):
        eye = []
        for x0, x1 in ((81, 136), (166, 218)):
            for y in range(187, 212, 2):
                for x in range(x0, x1, 3):
                    eye.append(map_to_cd(frame, x, y))
        # Under-eye/cheek regions are stable in the synthetic source. Subtracting
        # their mean rejects additive local illumination bias.
        cheek = []
        for x0, x1 in ((91, 127), (176, 213)):
            for y in range(230, 249, 3):
                for x in range(x0, x1, 3):
                    cheek.append(map_to_cd(frame, x, y))
        if not all(0 <= x < N and 0 <= y < N for x, y in eye + cheek):
            raise ValueError("An eye/cheek ROI falls outside the disc preview")
        result.append((eye, cheek))
    return result


def mean(x: list[float]) -> float:
    return sum(x) / len(x)


def gap_for(signal: list[float]) -> float:
    return mean([signal[i] for i in OPEN]) - mean([signal[i] for i in CLOSED])


def simulate_signal(samples: list[tuple[list[tuple[float, float, float]],
                                         list[tuple[float, float, float]]]],
                    contrast: float, glare: float, noise: float) -> list[float]:
    signals = []
    for eyes, cheeks in samples:
        eye_average = sum(perturb(v, x, y, contrast, glare, noise)
                          for v, x, y in eyes) / len(eyes)
        cheek_average = sum(perturb(v, x, y, contrast, glare, noise)
                            for v, x, y in cheeks) / len(cheeks)
        signals.append(eye_average - cheek_average)
    return signals


def cached_samples(pixels: bytes, integral: list[int],
                   regions: list[tuple[list[tuple[int, int]],
                                       list[tuple[int, int]]]],
                   radius: int) -> list[tuple[list[tuple[float, float, float]],
                                             list[tuple[float, float, float]]]]:
    out = []
    for eyes, cheeks in regions:
        sets = []
        for group in (eyes, cheeks):
            sets.append([(blur_at(pixels, integral, x, y, radius), x, y)
                         for x, y in group])
        out.append((sets[0], sets[1]))
    return out


def transform_whole_image(pixels: bytes, integral: list[int], output: Path,
                          contrast: float, radius: int, glare: float, noise: float) -> None:
    out = bytearray(N * N)
    for y in range(N):
        for x in range(N):
            v = blur_at(pixels, integral, x, y, radius)
            out[y * N + x] = round(perturb(v, x, y, contrast, glare, noise))
    write_gray_png(output, N, N, bytes(out))


def selftest() -> None:
    patch = bytes([40] * (N * N))
    integral = integral_image(patch, N, N)
    assert blur_at(patch, integral, 0, 0, 0) == 40
    assert blur_at(patch, integral, 399, 399, 8) == 40
    assert perturb(12, 0, 0, 0, 0, 0) == 165
    assert perturb(12, 0, 0, 1, 0, 0) == 12
    assert abs(noise_unit(200, 300)) <= 1
    assert len(roi_positions()) == 12
    assert gap_for([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) == 0
    print("optical-stress-selftest: PASS")


def run(path: Path, output_dir: Path) -> int:
    w, h, pixels = read_gray_png(path)
    if (w, h) != (N, N):
        raise ValueError("Expected full-capacity 800x800 CD digital readback")
    output_dir.mkdir(parents=True, exist_ok=True)
    integral = integral_image(pixels, N, N)
    positions = roi_positions()

    clean_samples = cached_samples(pixels, integral, positions, 0)
    reference_signal = simulate_signal(clean_samples, 1, 0, 0)
    clean_gap = gap_for(reference_signal)
    if abs(clean_gap) < GAP_THRESHOLD:
        raise ValueError(f"Pristine synthetic blink has insufficient gray gap: {clean_gap:.4f}")

    scenarios = []
    boundaries = []
    for radius in BLUR_RADII:
        blurred_samples = cached_samples(pixels, integral, positions, radius)
        for glare in GLARES:
            for noise in NOISE_AMPLITUDES:
                passes = []
                for contrast in CONTRASTS:
                    signal = simulate_signal(blurred_samples, contrast, glare, noise)
                    eye_gap = gap_for(signal)
                    temporal_r = correlation(reference_signal, signal)
                    survives = abs(eye_gap) >= GAP_THRESHOLD and temporal_r >= CORR_THRESHOLD
                    scenarios.append({
                        "contrast_fraction": contrast,
                        "box_blur_radius_pixels": radius,
                        "glare_peak_gray": glare,
                        "noise_peak_gray": noise,
                        "eye_open_closed_gap_gray_signed": round(eye_gap, 4),
                        "eye_open_closed_gap_gray_absolute": round(abs(eye_gap), 4),
                        "temporal_pearson_r": round(temporal_r, 5),
                        "model_survives": survives,
                    })
                    if survives:
                        passes.append(contrast)
                boundaries.append({
                    "box_blur_radius_pixels": radius,
                    "glare_peak_gray": glare,
                    "noise_peak_gray": noise,
                    "lowest_tested_surviving_contrast_fraction": min(passes) if passes else None,
                    "no_survival_in_grid": not bool(passes),
                })

    # Invariants: an unmodified frame must pass; removing ALL contrast and
    # without glare/noise must fail; at least one realistic stress case must fail.
    lookup = {(x["contrast_fraction"], x["box_blur_radius_pixels"],
               x["glare_peak_gray"], x["noise_peak_gray"]): x for x in scenarios}
    clean = lookup[(1.0, 0, 0, 0)]
    erased = lookup[(0.0, 0, 0, 0)]
    if not clean["model_survives"] or erased["model_survives"]:
        raise AssertionError("Optical model fails clean/erased-control gate")
    if not any(not row["model_survives"] for row in scenarios):
        raise AssertionError("Stress simulation did not detect any failed conditions")
    # Monotone loss as only contrast decreases: a fundamental sanity check.
    for radius in BLUR_RADII:
        family = [lookup[(contrast, radius, 0, 0)] for contrast in CONTRASTS]
        passed_levels = [x["contrast_fraction"] for x in family if x["model_survives"]]
        if passed_levels and any(
            x["contrast_fraction"] > min(passed_levels) and not x["model_survives"]
            for x in family
        ):
            raise AssertionError(f"Nonmonotonic ideal-illumination contrast sweep: blur={radius}")

    report = {
        "gate": "PASS",
        "gate_definition": "simulation executed, clean and erased controls behave correctly",
        "not_a_physical_pass": True,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": "single synthetic 12-frame CD readback, no calibrated CD-R/LED/camera inputs",
        "model": {
            "resolution": [N, N],
            "contrast_definition": "linear scaling about 165 gray, fraction 0..1",
            "blur_definition": "box blur radius in 800px disc-preview coordinates",
            "glare_definition": "additive camera-space elliptical Gaussian highlight in gray units",
            "noise_definition": "deterministic per-pixel uniform-like additive gray noise, peak amplitude",
            "eye_motion_metric": "mean eye brightness minus stable cheek brightness across 12 sectors",
            "assumed_survival_heuristic": {
                "minimum_absolute_open_minus_closed_gray": GAP_THRESHOLD,
                "minimum_temporal_correlation": CORR_THRESHOLD,
            },
            "open_frame_indices": list(OPEN),
            "closed_frame_indices": list(CLOSED),
            "contrast_steps": list(CONTRASTS),
            "blur_radius_steps": list(BLUR_RADII),
            "glare_steps": list(GLARES),
            "noise_steps": list(NOISE_AMPLITUDES),
        },
        "baseline_eye_gap_gray_signed": round(clean_gap, 4),
        "baseline_eye_gap_gray_absolute": round(abs(clean_gap), 4),
        "total_tested_conditions": len(scenarios),
        "surviving_conditions": sum(x["model_survives"] for x in scenarios),
        "failed_conditions": sum(not x["model_survives"] for x in scenarios),
        "lowest_tested_contrast_without_glare_or_noise": {
            str(radius): next(
                (row["lowest_tested_surviving_contrast_fraction"] for row in boundaries
                 if row["box_blur_radius_pixels"] == radius
                 and row["glare_peak_gray"] == row["noise_peak_gray"] == 0),
                None,
            ) for radius in BLUR_RADII
        },
        "survival_boundaries": boundaries,
        "scenarios": scenarios,
        "limitations": [
            "Contrast, glare, blur and noise are arbitrary synthetic parameters, not measured optical reflectance.",
            "Digital contrast and eye-motion correlations do not establish human visual recognition.",
            "Glare model is static; motor instability, shutter phase, sector masking, strobing and lighting hazards are not simulated.",
            "Cannot infer minimum required real CD-R contrast or a safe physical strobe setting from these results.",
            "Do not represent encoded image-pattern WAV as a commercial music Audio CD.",
        ],
    }
    (output_dir / "optical-stress-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    transform_whole_image(pixels, integral, output_dir / "mild-stress.png",
                          contrast=0.5, radius=2, glare=45, noise=10)
    transform_whole_image(pixels, integral, output_dir / "severe-stress.png",
                          contrast=0.10, radius=8, glare=100, noise=10)
    print("optical-stress: PASS | "
          f"clean-gap={clean_gap:.2f}/255 | "
          f"survive={report['surviving_conditions']}/{len(scenarios)} | "
          f"ideal-boundaries={report['lowest_tested_contrast_without_glare_or_noise']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.readback is None or args.out is None:
        parser.error("--readback and --out are required unless --selftest")
    return run(args.readback, args.out)


if __name__ == "__main__":
    raise SystemExit(main())

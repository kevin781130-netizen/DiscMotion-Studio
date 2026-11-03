# DiscMotion Studio — Zoetrope Prototype v1

Independent **offline, non-burning** tool. Generates a static 12-sector grayscale PNG and a browser preview from **exactly 12 sequential images**. Does not modify the upstream optical-disc encoder, Windows GUI, or main branch.

## Requirements
- .NET 10 SDK (same as upstream `global.json`).
- No new NuGet packages: references upstream `DiscImageStudio.ImageIO`.

## Inputs
Place exactly 12 portrait frames in a folder, named in order `00.png` ... `11.png`. Images can also be JPEG/BMP/GIF (GIF's **first frame only**). Use identical framing and high-contrast artwork. The output is deliberately grayscale. Recommended loop: open eyes -> close -> open.

## Run

```powershell
dotnet run --project tools/Zoetrope -- --selftest
dotnet run --project tools/Zoetrope -- render --frames .\portraits --out .\zoetrope-output
```

The output directory must not already contain files. Open `zoetrope-output/preview.html` in a browser; `disc.png` is a 2400 x 2400 Gray8 image to import into DiscImageStudio's design page.

## Layout geometry
- 120 mm nominal disc; 20 pixels/mm, canvas center (1200, 1200).
- 25–57 mm radius (the printed disc's physical writable ring may differ).
- 12 clockwise sectors, 30 degrees per frame; each sector carries the corresponding still image, with a thin white gutter.
- Still images are unwrapped angularly/radially into a wedge. Photo fidelity can suffer due to distortion, contrast loss and track rasterization.
- Default preview: 120 RPM, 24 Hz simulated strobe. At a physical fixed observation window, each flash samples the next of the 12 frames.

The preview displays a rotating ring and a **digital fixed-window approximation**. A real demonstration also needs a stable spindle, synchronized illumination/camera and an aperture/mask covering all but one sector. Do not interpret the preview as a validated optical effect. Photosensitive viewers should avoid direct strobe viewing.

**Important:** The generated PNG is an image pattern **only**. Burning it with DiscImageStudio does **not** create an ordinary Audio CD with playable music. DiscImageStudio's physical projection and CD geometry require actual burn and calibration trials; CD-R contrast, orientation, and legibility are unverified.

The original project's GPL-3.0-or-later and dependency notices continue to apply.

using DiscImageStudio.ImageIO;

namespace DiscMotionStudio.Zoetrope;

/// <summary>
/// Offline, non-burning 12-frame disc layout. Physical contrast and timing
/// must be validated with actual media before commercial use.
/// </summary>
internal static class Program
{
    private const int Count = 12;
    private const int CanvasSize = 2400;
    private const int Center = CanvasSize / 2;
    // The image canvas represents a 120 mm disc at 20 px/mm.
    private const int InnerRadius = 500; // 25 mm
    private const int OuterRadius = 1140; // 57 mm
    private const double SectorGutter = 0.025;
    private const long MaxInputBytes = 32L * 1024 * 1024;
    private const long MaxInputPixels = 4L * 1024 * 1024;

    private static int Main(string[] args)
    {
        try
        {
            if (args is ["--selftest"])
            {
                SelfTest();
                Console.WriteLine("zoetrope-selftest: PASS");
                return 0;
            }
            if (args is not ["render", "--frames", _, "--out", _])
            {
                Console.WriteLine("Zoetrope disc image generator (non-burning proof of concept)");
                Console.WriteLine("  dotnet run --project tools/Zoetrope -- render --frames INPUT_DIR --out OUTPUT_DIR");
                Console.WriteLine("  dotnet run --project tools/Zoetrope -- --selftest");
                return args.Length == 0 || args[0] is "--help" or "-h" ? 0 : 2;
            }

            RenderCommand(args[2], args[4]);
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"zoetrope: {e.Message}");
            return 1;
        }
    }

    private static void RenderCommand(string inputDirectory, string outputDirectory)
    {
        string sourceDir = Path.GetFullPath(inputDirectory);
        string outputDir = Path.GetFullPath(outputDirectory);
        if (!Directory.Exists(sourceDir))
            throw new DirectoryNotFoundException($"Missing frames directory: {sourceDir}");

        string[] paths = Directory.EnumerateFiles(sourceDir)
            .Where(path => new[] { ".png", ".jpg", ".jpeg", ".bmp", ".gif" }
                .Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase))
            .OrderBy(path => Path.GetFileName(path), StringComparer.Ordinal)
            .ToArray();

        if (paths.Length != Count)
            throw new ArgumentException($"Expected exactly {Count} numbered image frames; found {paths.Length}.");
        if (Directory.Exists(outputDir) && Directory.EnumerateFileSystemEntries(outputDir).Any())
            throw new IOException("Output directory must be empty to prevent overwriting files.");

        BgraRaster[] frames = paths.Select(path =>
            RasterCodec.LoadBgra32(path, MaxInputBytes, MaxInputPixels)).ToArray();

        byte[] layout = RenderRing(frames);
        Directory.CreateDirectory(outputDir);
        RasterCodec.SavePng(Path.Combine(outputDir, "disc.png"), CanvasSize, CanvasSize, layout, grayscale: true);

        // Copy scaled grayscale stills into the preview package, so preview.html
        // works offline even when the input directory is moved or deleted.
        for (int i = 0; i < Count; i++)
        {
            byte[] thumbnail = CreateThumbnail(frames[i], 300, 450);
            RasterCodec.SavePng(Path.Combine(outputDir, $"frame_{i:00}.png"),
                300, 450, thumbnail, grayscale: true);
        }

        string template = Path.Combine(AppContext.BaseDirectory, "preview.template.html");
        File.Copy(template, Path.Combine(outputDir, "preview.html"));
        Console.WriteLine($"Generated: {Path.Combine(outputDir, "disc.png")}");
        Console.WriteLine($"Preview:   {Path.Combine(outputDir, "preview.html")}");
        Console.WriteLine("This does not write a disc or guarantee a playable Audio CD.");
    }

    private static byte[] RenderRing(IReadOnlyList<BgraRaster> frames)
    {
        if (frames.Count != Count)
            throw new ArgumentException($"Exactly {Count} frames are required.", nameof(frames));
        if (frames.Any(frame => frame.Width <= 0 || frame.Height <= 0 ||
            frame.Pixels.Length != checked(frame.Width * frame.Height * 4)))
            throw new ArgumentException("Invalid frame dimensions or BGRA buffer.", nameof(frames));

        byte[] output = new byte[CanvasSize * CanvasSize];
        Array.Fill(output, (byte)255);
        for (int y = 0; y < CanvasSize; y++)
        {
            int dy = y - Center;
            for (int x = 0; x < CanvasSize; x++)
            {
                int dx = x - Center;
                double radius = Math.Sqrt((double)dx * dx + (double)dy * dy);
                if (radius < InnerRadius || radius > OuterRadius) continue;

                // Zero points to 12 o'clock; increasing angles run clockwise.
                double angle = Math.Atan2(dx, -dy);
                if (angle < 0) angle += 2 * Math.PI;
                double sectorPosition = angle * Count / (2 * Math.PI);
                int index = Math.Min((int)sectorPosition, Count - 1);
                double within = sectorPosition - index;
                if (within <= SectorGutter || within >= 1 - SectorGutter) continue;

                BgraRaster source = frames[index];
                double u = (within - SectorGutter) / (1 - 2 * SectorGutter);
                double v = (OuterRadius - radius) / (OuterRadius - InnerRadius);
                int sourceX = Math.Clamp((int)(u * source.Width), 0, source.Width - 1);
                int sourceY = Math.Clamp((int)(v * source.Height), 0, source.Height - 1);
                output[y * CanvasSize + x] = Gray(source, sourceX, sourceY);
            }
        }
        return output;
    }

    private static byte[] CreateThumbnail(BgraRaster source, int width, int height)
    {
        byte[] result = new byte[width * height];
        for (int y = 0; y < height; y++)
        for (int x = 0; x < width; x++)
        {
            int sx = Math.Min((int)((long)x * source.Width / width), source.Width - 1);
            int sy = Math.Min((int)((long)y * source.Height / height), source.Height - 1);
            result[y * width + x] = Gray(source, sx, sy);
        }
        return result;
    }

    private static byte Gray(BgraRaster raster, int x, int y)
    {
        int p = checked((y * raster.Width + x) * 4);
        int b = raster.Pixels[p];
        int g = raster.Pixels[p + 1];
        int r = raster.Pixels[p + 2];
        int a = raster.Pixels[p + 3];
        int brightness = (2126 * r + 7152 * g + 722 * b + 5000) / 10000;
        return (byte)((brightness * a + 255 * (255 - a) + 127) / 255);
    }

    private static void SelfTest()
    {
        // A synthetic 12-frame fixture proves sector order, empty hub, image
        // dimensions, deterministic output, and local PNG encode/decode.
        BgraRaster[] frames = Enumerable.Range(0, Count).Select(index =>
        {
            byte intensity = (byte)(index * 20);
            byte[] pixels = new byte[8 * 8 * 4];
            for (int offset = 0; offset < pixels.Length; offset += 4)
            {
                pixels[offset] = intensity;
                pixels[offset + 1] = intensity;
                pixels[offset + 2] = intensity;
                pixels[offset + 3] = 255;
            }
            return new BgraRaster(8, 8, pixels);
        }).ToArray();

        byte[] result = RenderRing(frames);
        if (result.Length != CanvasSize * CanvasSize || result[Center * CanvasSize + Center] != 255)
            throw new InvalidOperationException("Canvas dimensions or central hub are incorrect.");

        for (int i = 0; i < Count; i++)
        {
            double angle = (i + 0.5) * (2 * Math.PI / Count);
            int x = Center + (int)Math.Round(800 * Math.Sin(angle));
            int y = Center - (int)Math.Round(800 * Math.Cos(angle));
            if (result[y * CanvasSize + x] != (byte)(i * 20))
                throw new InvalidOperationException($"Incorrect clockwise sector at frame {i}.");
        }

        if (!result.SequenceEqual(RenderRing(frames)))
            throw new InvalidOperationException("Non-deterministic layout generation.");

        string temp = Path.Combine(Path.GetTempPath(), $"zoetrope-{Guid.NewGuid():N}.png");
        try
        {
            RasterCodec.SavePng(temp, CanvasSize, CanvasSize, result, grayscale: true);
            BgraRaster decoded = RasterCodec.LoadBgra32(temp, MaxInputBytes, CanvasSize * CanvasSize);
            if (decoded.Width != CanvasSize || decoded.Height != CanvasSize)
                throw new InvalidOperationException("PNG roundtrip dimensions differ.");
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }

        if (Gray(new BgraRaster(1, 1, [0, 0, 0, 0]), 0, 0) != 255)
            throw new InvalidOperationException("Transparent pixels must composite over white.");
    }
}

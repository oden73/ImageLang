using System;
using System.Drawing;
using System.IO;

namespace ImageLangRuntime
{
    public class ImageWrapper
    {
        public Bitmap Bitmap { get; private set; }
        public ImageWrapper(string path) {
            if (!File.Exists(path)) throw new FileNotFoundException("File not found: " + path);
            Bitmap = new Bitmap(path);
        }
        public ImageWrapper(int w, int h) { Bitmap = new Bitmap(w, h); }
        public ImageWrapper(Bitmap bmp) { Bitmap = bmp; }
    }

    public struct LangColor {
        public int r, g, b;
        public LangColor(int r, int g, int b) { this.r = r; this.g = g; this.b = b; }
    }

    public static class Ops
    {
        public static object Add(object a, object b) {
            if (a is string || b is string) return $"{a}{b}";
            if (a is ImageWrapper i1 && b is ImageWrapper i2) return StdLib.add_images(i1, i2);
            double r = ToDouble(a) + ToDouble(b);
            return IsInt(a) && IsInt(b) ? (object)(int)r : r;
        }

        public static object Sub(object a, object b) {
            if (a is ImageWrapper i1 && b is ImageWrapper i2) return StdLib.sub_images(i1, i2);
            
            // Debug для проверки null
            if (a is ImageWrapper && b == null) { Console.WriteLine("[Runtime Error] Sub: second image is null!"); return a; }
            if (a == null && b is ImageWrapper) { Console.WriteLine("[Runtime Error] Sub: first image is null!"); return b; }

            double r = ToDouble(a) - ToDouble(b);
            return IsInt(a) && IsInt(b) ? (object)(int)r : r;
        }

        public static object Mul(object a, object b) {
            if (a is ImageWrapper i && IsNum(b)) return StdLib.mul_image_scalar(i, ToDouble(b));
            if (b is ImageWrapper i2 && IsNum(a)) return StdLib.mul_image_scalar(i2, ToDouble(a));
            double r = ToDouble(a) * ToDouble(b);
            return IsInt(a) && IsInt(b) ? (object)(int)r : r;
        }

        public static object Div(object a, object b) {
            double r = ToDouble(a) / ToDouble(b);
            return IsInt(a) && IsInt(b) ? (object)(int)r : r;
        }

        public static object Neg(object a) {
            double d = ToDouble(a);
            // Если исходное было int, вернем int. Иначе double.
            return IsInt(a) ? (object)(int)(-d) : -d;
        }
        
        public static object Gt(object a, object b) => ToDouble(a) > ToDouble(b);
        
        public static object Lt(object a, object b) => ToDouble(a) < ToDouble(b);
        
        public static object Eq(object a, object b) 
        {
            if (a == null && b == null) return true;
            if (a == null || b == null) return false;
            // Для чисел сравнение через Equals может сбоить (int vs double),
            // но для базового теста хватит.
            return a.Equals(b);
        }

        // Обертки
        public static object Load(object path) => StdLib.load(path?.ToString());
        public static void Save(object img, object path) => StdLib.save(img as ImageWrapper, path?.ToString());
        public static object Pow(object img, object g) => StdLib.pow_channels(img as ImageWrapper, ToDouble(g));
        public static object Blur(object img, object r) => StdLib.blur(img as ImageWrapper, ToDouble(r));
        public static object Width(object img) => StdLib.width(img as ImageWrapper);
        public static object Height(object img) => StdLib.height(img as ImageWrapper);
        public static object GetPixel(object img, object x, object y) => StdLib.get_pixel(img as ImageWrapper, (int)ToDouble(x), (int)ToDouble(y));
        public static double Avg(object img) => StdLib.avg(img as ImageWrapper);

        private static double ToDouble(object o) => Convert.ToDouble(o);
        private static bool IsInt(object o) => o is int;
        private static bool IsNum(object o) => o is int || o is double || o is float;
    }

    public static class StdLib
    {
        public static void write(object obj) => Console.WriteLine(obj?.ToString() ?? "null");
        public static string read_string() => Console.ReadLine()?.Trim();

        public static ImageWrapper load(string path) {
            try { return new ImageWrapper(path); } catch { return null; }
        }
        public static void save(ImageWrapper img, string path) {
            if (img != null) img.Bitmap.Save(path);
        }
        public static int width(ImageWrapper img) => img?.Bitmap.Width ?? 0;
        public static int height(ImageWrapper img) => img?.Bitmap.Height ?? 0;
        
        public static LangColor get_pixel(ImageWrapper img, int x, int y) {
            if (img == null) return new LangColor();
            Color c = img.Bitmap.GetPixel(x, y);
            return new LangColor(c.R, c.G, c.B);
        }

        public static ImageWrapper pow_channels(ImageWrapper img, double gamma) {
            if (img == null) return null;
            Bitmap res = new Bitmap(img.Bitmap.Width, img.Bitmap.Height);
            for(int x=0;x<res.Width;x++) for(int y=0;y<res.Height;y++) {
                Color c = img.Bitmap.GetPixel(x, y);
                res.SetPixel(x, y, Color.FromArgb(Clamp(255 * Math.Pow(c.R/255.0, gamma)), Clamp(255 * Math.Pow(c.G/255.0, gamma)), Clamp(255 * Math.Pow(c.B/255.0, gamma))));
            }
            return new ImageWrapper(res);
        }

        public static ImageWrapper blur(ImageWrapper img, double r)
        {
            if (img == null) return null;
            
            // Если радиус маленький, нет смысла размывать
            int radius = (int)Math.Ceiling(r);
            if (radius < 1) return new ImageWrapper((Bitmap)img.Bitmap.Clone());

            Bitmap src = img.Bitmap;
            Bitmap dest = new Bitmap(src.Width, src.Height);

            // Простой алгоритм Box Blur (усрелнение соседей)
            // Это не самый быстрый способ (GetPixel медленный), но для лабы идеально понятный
            for (int x = 0; x < src.Width; x++)
            {
                for (int y = 0; y < src.Height; y++)
                {
                    long rSum = 0, gSum = 0, bSum = 0;
                    int count = 0;

                    // Проходим по соседям от (x-radius) до (x+radius)
                    for (int kx = x - radius; kx <= x + radius; kx++)
                    {
                        for (int ky = y - radius; ky <= y + radius; ky++)
                        {
                            // Проверка границ изображения
                            if (kx >= 0 && kx < src.Width && ky >= 0 && ky < src.Height)
                            {
                                Color c = src.GetPixel(kx, ky);
                                rSum += c.R;
                                gSum += c.G;
                                bSum += c.B;
                                count++;
                            }
                        }
                    }

                    // Записываем среднее значение
                    dest.SetPixel(x, y, Color.FromArgb(
                        (int)(rSum / count),
                        (int)(gSum / count),
                        (int)(bSum / count)));
                }
            }
            return new ImageWrapper(dest);
        }

        public static double avg(ImageWrapper img) {
            if (img == null) return 0.0;
            long sum = 0;
            int w = img.Bitmap.Width;
            int h = img.Bitmap.Height;
            if (w == 0 || h == 0) return 0.0; // Защита от NaN

            for(int x=0; x<w; x++) for(int y=0; y<h; y++) {
                Color c = img.Bitmap.GetPixel(x, y);
                sum += (c.R + c.G + c.B) / 3;
            }
            return sum / (double)(w * h);
        }

        public static ImageWrapper add_images(ImageWrapper a, ImageWrapper b) {
            if (a == null) return b; if (b == null) return a;
            int w = Math.Min(a.Bitmap.Width, b.Bitmap.Width);
            int h = Math.Min(a.Bitmap.Height, b.Bitmap.Height);
            Bitmap res = new Bitmap(w, h);
            for (int x = 0; x < w; x++) for (int y = 0; y < h; y++) {
                Color c1 = a.Bitmap.GetPixel(x, y);
                Color c2 = b.Bitmap.GetPixel(x, y);
                res.SetPixel(x, y, Color.FromArgb(Clamp(c1.R+c2.R), Clamp(c1.G+c2.G), Clamp(c1.B+c2.B)));
            }
            return new ImageWrapper(res);
        }

        public static ImageWrapper sub_images(ImageWrapper a, ImageWrapper b) {
            if (a == null) return null; if (b == null) return a;
            int w = Math.Min(a.Bitmap.Width, b.Bitmap.Width);
            int h = Math.Min(a.Bitmap.Height, b.Bitmap.Height);
            Bitmap res = new Bitmap(w, h);
            for (int x = 0; x < w; x++) for (int y = 0; y < h; y++) {
                Color c1 = a.Bitmap.GetPixel(x, y);
                Color c2 = b.Bitmap.GetPixel(x, y);
                // ИСПОЛЬЗУЕМ МОДУЛЬ РАЗНОСТИ (Math.Abs)
                res.SetPixel(x, y, Color.FromArgb(
                    Clamp(Math.Abs(c1.R - c2.R)), 
                    Clamp(Math.Abs(c1.G - c2.G)), 
                    Clamp(Math.Abs(c1.B - c2.B))));
            }
            return new ImageWrapper(res);
        }

        public static ImageWrapper mul_image_scalar(ImageWrapper img, double v) {
            if (img == null) return null;
            Bitmap res = new Bitmap(img.Bitmap.Width, img.Bitmap.Height);
            for(int x=0;x<res.Width;x++) for(int y=0;y<res.Height;y++) {
                Color c = img.Bitmap.GetPixel(x, y);
                res.SetPixel(x, y, Color.FromArgb(Clamp(c.R*v), Clamp(c.G*v), Clamp(c.B*v)));
            }
            return new ImageWrapper(res);
        }

        private static int Clamp(double v) => Math.Max(0, Math.Min(255, (int)v));
    }
}
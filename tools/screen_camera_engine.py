"""Procedural macro-screen video engine.

Render a deterministic Windows-like desktop, a Chrome double-click, and a
handheld camera passing close to an RGB LCD panel. No input footage is needed.

Every rendered frame is also written as a still image to images/ (180 files for
the default 6 s @ 30 fps). Pass --no-frames to encode the video only.

Example:
    python tools/screen_camera_engine.py
    python tools/screen_camera_engine.py --still files/screen_preview.jpg --at 4.8
    python tools/screen_camera_engine.py --no-frames
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = Path("C:/Windows/Fonts")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        path = FONT_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    return t * t * (3.0 - 2.0 * t)


def centered_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
                  text_font: ImageFont.ImageFont, fill: tuple[int, ...]) -> None:
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1]), text, font=text_font, fill=fill)


def chrome_icon(size: int) -> Image.Image:
    s = size * 4
    image = Image.new("RGBA", (s, s))
    draw = ImageDraw.Draw(image)
    pad = int(s * 0.055)
    box = (pad, pad, s - pad, s - pad)
    draw.ellipse((pad + 5, pad + 10, s - pad + 5, s - pad + 10), fill=(0, 0, 0, 65))
    for start, end, color in [
        (180, 300, (234, 67, 53, 255)),
        (300, 60, (251, 188, 5, 255)),
        (60, 180, (52, 168, 83, 255)),
    ]:
        draw.pieslice(box, start=start, end=end, fill=color)
    c = s // 2
    draw.ellipse((c - int(s * .245), c - int(s * .245), c + int(s * .245), c + int(s * .245)),
                 fill=(255, 255, 255, 255))
    draw.ellipse((c - int(s * .184), c - int(s * .184), c + int(s * .184), c + int(s * .184)),
                 fill=(66, 133, 244, 255))
    draw.arc((c - int(s * .171), c - int(s * .171), c + int(s * .171), c + int(s * .171)),
             205, 320, fill=(116, 169, 249, 255), width=max(2, int(s * .018)))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def simple_icon(kind: str, size: int = 58) -> Image.Image:
    s = size * 4
    im = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(im)
    if kind == "pc":
        d.rounded_rectangle((20, 30, s - 20, s * .69), radius=16, fill=(225, 239, 248, 255))
        d.rounded_rectangle((34, 44, s - 34, s * .64), radius=9, fill=(56, 145, 202, 255))
        d.polygon([(s * .4, s * .69), (s * .6, s * .69), (s * .66, s * .83), (s * .34, s * .83)],
                  fill=(197, 213, 222, 255))
        d.rounded_rectangle((s * .28, s * .81, s * .72, s * .88), radius=8, fill=(229, 237, 241, 255))
    elif kind == "bin":
        d.polygon([(s * .28, s * .25), (s * .75, s * .25), (s * .68, s * .86), (s * .35, s * .86)],
                  fill=(222, 239, 241, 245), outline=(143, 183, 190, 255))
        d.rounded_rectangle((s * .24, s * .19, s * .79, s * .27), radius=8, fill=(187, 220, 226, 255))
        d.rounded_rectangle((s * .40, s * .12, s * .63, s * .21), radius=7, fill=(210, 232, 235, 255))
        for x in (.40, .51, .62):
            d.line((s * x, s * .34, s * (x - .025), s * .73), fill=(119, 189, 182, 255), width=8)
    else:
        d.rounded_rectangle((s * .11, s * .27, s * .88, s * .79), radius=15, fill=(240, 179, 54, 255))
        d.rounded_rectangle((s * .12, s * .19, s * .47, s * .38), radius=12, fill=(255, 205, 92, 255))
        d.rounded_rectangle((s * .11, s * .35, s * .88, s * .82), radius=15, fill=(255, 198, 70, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)


def cursor_image() -> Image.Image:
    s = 4
    im = Image.new("RGBA", (31 * s, 43 * s))
    d = ImageDraw.Draw(im)
    points = [(3, 2), (5, 34), (12, 27), (18, 40), (24, 37), (18, 25), (28, 24)]
    points = [(x * s, y * s) for x, y in points]
    d.polygon([(x + 4, y + 5) for x, y in points], fill=(0, 0, 0, 75))
    d.polygon(points, fill=(250, 250, 250, 255), outline=(20, 24, 28, 255), width=4)
    return im.resize((31, 43), Image.Resampling.LANCZOS)


class Desktop:
    def __init__(self, width: int = 1600, height: int = 900):
        self.w, self.h = width, height
        self.chrome_center = (480, 283)
        self.cursor = cursor_image()
        self.chrome = chrome_icon(82)
        self.base = self._desktop()
        self.browser = self._browser(680, 440)

    def _desktop(self) -> Image.Image:
        y, x = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        xn, yn = x / self.w, y / self.h
        base = np.zeros((self.h, self.w, 3), np.float32)
        base[:] = (8, 30, 58)
        base += ((1 - yn) * 13)[..., None] * np.array([.15, .65, 1.0], np.float32)
        for cx, cy, sx, sy, color, strength in [
            (.72, .20, .36, .33, (22, 108, 177), 1.0),
            (.34, .72, .42, .26, (15, 86, 135), .8),
            (.90, .88, .27, .40, (32, 122, 158), .7),
        ]:
            g = np.exp(-(((xn - cx) / sx) ** 2 + ((yn - cy) / sy) ** 2) * 2.0)[..., None]
            base += g * np.array(color, np.float32) * strength
        wave = np.exp(-((yn - (.48 + .13 * np.sin(xn * 5.2))) / .12) ** 2)[..., None]
        base += wave * np.array((5, 23, 36), np.float32)
        image = Image.fromarray(np.uint8(np.clip(base, 0, 255)), "RGB").convert("RGBA")
        d = ImageDraw.Draw(image)
        d.rectangle((0, self.h - 52, self.w, self.h), fill=(18, 27, 36, 244))
        for x0, label, kind in [(90, "This PC", "pc"), (90, "Recycle Bin", "bin"),
                                (90, "Documents", "folder")]:
            y0 = 48 if label == "This PC" else (198 if label == "Recycle Bin" else 348)
            icon = simple_icon(kind)
            image.alpha_composite(icon, (x0, y0))
            d.text((x0 + 29, y0 + 63), label, font=font(15), fill=(0, 0, 0, 210), anchor="mt")
            d.text((x0 + 29, y0 + 62), label, font=font(15), fill=(245, 249, 252, 255), anchor="mt")
        cx, cy = self.chrome_center
        image.alpha_composite(self.chrome, (cx - 41, cy - 41))
        d.text((cx, cy + 47), "Google Chrome", font=font(16), fill=(0, 0, 0, 220), anchor="mt")
        d.text((cx, cy + 46), "Google Chrome", font=font(16), fill=(250, 252, 255, 255), anchor="mt")
        small_chrome = chrome_icon(28)
        image.alpha_composite(small_chrome, (self.w // 2 - 76, self.h - 40))
        d.rounded_rectangle((self.w // 2 - 150, self.h - 42, self.w // 2 - 96, self.h - 10),
                            radius=8, fill=(43, 55, 66, 255))
        d.ellipse((self.w // 2 - 137, self.h - 34, self.w // 2 - 119, self.h - 16),
                  outline=(196, 211, 222, 255), width=2)
        d.line((self.w // 2 - 121, self.h - 18, self.w // 2 - 114, self.h - 12),
               fill=(196, 211, 222, 255), width=2)
        d.text((self.w - 104, self.h - 35), "10:24", font=font(14), fill=(232, 238, 242, 255))
        return image

    def _browser(self, w: int, h: int) -> Image.Image:
        im = Image.new("RGBA", (w, h), (250, 251, 253, 255))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=13, fill=(249, 250, 252, 255),
                            outline=(137, 145, 153, 255), width=1)
        d.rounded_rectangle((1, 1, w - 2, 58), radius=12, fill=(222, 226, 232, 255))
        d.rectangle((1, 44, w - 2, 58), fill=(222, 226, 232, 255))
        d.rounded_rectangle((15, 9, 243, 57), radius=12, fill=(255, 255, 255, 255))
        d.rectangle((15, 40, 243, 57), fill=(255, 255, 255, 255))
        im.alpha_composite(chrome_icon(23), (28, 20))
        d.text((59, 22), "New tab", font=font(16), fill=(43, 47, 52, 255))
        d.line((220, 27, 232, 39), fill=(88, 94, 101, 255), width=2)
        d.line((232, 27, 220, 39), fill=(88, 94, 101, 255), width=2)
        d.line((263, 27, 275, 39), fill=(85, 91, 98, 255), width=2)
        d.line((275, 27, 263, 39), fill=(85, 91, 98, 255), width=2)
        for x in (w - 104, w - 68, w - 32):
            if x == w - 104:
                d.line((x - 7, 30, x + 7, 30), fill=(71, 76, 82, 255), width=2)
            elif x == w - 68:
                d.rectangle((x - 7, 23, x + 7, 37), outline=(71, 76, 82, 255), width=2)
            else:
                d.line((x - 7, 23, x + 7, 37), fill=(71, 76, 82, 255), width=2)
                d.line((x + 7, 23, x - 7, 37), fill=(71, 76, 82, 255), width=2)
        d.rectangle((1, 58, w - 2, 111), fill=(255, 255, 255, 255))
        for x, symbol in [(30, "‹"), (63, "›")]:
            d.text((x, 69), symbol, font=font(34), fill=(94, 100, 106, 255), anchor="mt")
        d.arc((91, 72, 113, 95), 35, 320, fill=(94, 100, 106, 255), width=2)
        d.polygon([(109, 70), (115, 73), (109, 77)], fill=(94, 100, 106, 255))
        d.rounded_rectangle((128, 69, w - 28, 102), radius=16, fill=(239, 241, 244, 255))
        d.rounded_rectangle((145, 77, 156, 88), radius=3, outline=(103, 110, 116, 255), width=1)
        d.arc((147, 73, 154, 82), 180, 360, fill=(103, 110, 116, 255), width=1)
        d.text((169, 77), "Search Google or type a URL", font=font(14), fill=(99, 105, 112, 255))
        logo_font = font(60, True)
        letters = [("G", (66, 133, 244, 255)), ("o", (234, 67, 53, 255)),
                   ("o", (251, 188, 5, 255)), ("g", (66, 133, 244, 255)),
                   ("l", (52, 168, 83, 255)), ("e", (234, 67, 53, 255))]
        widths = [d.textlength(c, font=logo_font) for c, _ in letters]
        lx = (w - sum(widths)) / 2
        for (char, color), cw in zip(letters, widths):
            d.text((lx, 139), char, font=logo_font, fill=color)
            lx += cw
        d.rounded_rectangle((112, 231, w - 112, 284), radius=26, fill=(255, 255, 255, 255),
                            outline=(210, 214, 219, 255), width=2)
        d.ellipse((140, 246, 156, 262), outline=(115, 122, 129, 255), width=2)
        d.line((153, 259, 160, 266), fill=(115, 122, 129, 255), width=2)
        d.text((174, 245), "Search Google or type a URL", font=font(16), fill=(122, 128, 135, 255))
        d.rounded_rectangle((w / 2 - 130, 307, w / 2 - 7, 339), radius=6, fill=(242, 244, 247, 255))
        d.rounded_rectangle((w / 2 + 8, 307, w / 2 + 130, 339), radius=6, fill=(242, 244, 247, 255))
        centered_text(d, (w / 2 - 68, 314), "Google Search", font(13), (66, 70, 75, 255))
        centered_text(d, (w / 2 + 69, 314), "I'm Feeling Lucky", font(13), (66, 70, 75, 255))
        return im

    def frame(self, t: float) -> Image.Image:
        im = self.base.copy()
        d = ImageDraw.Draw(im)
        cx, cy = self.chrome_center
        if 2.02 <= t < 3.05:
            d.rounded_rectangle((cx - 81, cy + 39, cx + 81, cy + 70), radius=4,
                                fill=(33, 105, 157, 175))
            d.text((cx, cy + 46), "Google Chrome", font=font(16), fill=(255, 255, 255, 255), anchor="mt")
        if t < 1.72:
            p = ease((t - .45) / 1.27)
            mx = 785 + (cx + 7 - 785) * p
            my = 495 + (cy + 9 - 495) * p
        elif t < 3.45:
            mx, my = cx + 7, cy + 9
        else:
            p = ease((t - 3.45) / 1.0)
            mx, my = (cx + 7) + 260 * p, (cy + 9) + 245 * p
        if t >= 2.83:
            p = ease((t - 2.83) / .66)
            bw, bh = self.browser.size
            scale = .16 + .84 * (1 - (1 - p) ** 3)
            size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
            browser = self.browser.resize(size, Image.Resampling.LANCZOS)
            if p < 1:
                alpha = browser.getchannel("A").point(lambda a: int(a * min(1, p * 2.4)))
                browser.putalpha(alpha)
            final_center = np.array((550, 375), np.float32)
            start_center = np.array((cx, cy), np.float32)
            center = start_center * (1 - p) + final_center * p
            shadow = Image.new("RGBA", im.size)
            sd = ImageDraw.Draw(shadow)
            x0, y0 = int(center[0] - size[0] / 2), int(center[1] - size[1] / 2)
            sd.rounded_rectangle((x0 + 5, y0 + 9, x0 + size[0] + 5, y0 + size[1] + 9),
                                 radius=13, fill=(0, 0, 0, int(85 * p)))
            shadow = shadow.filter(ImageFilter.GaussianBlur(9))
            im = Image.alpha_composite(im, shadow)
            im.alpha_composite(browser, (x0, y0))
        im.alpha_composite(self.cursor, (int(mx), int(my)))
        if 2.31 < t < 3.47:
            spin = Image.new("RGBA", (42, 42))
            sd = ImageDraw.Draw(spin)
            start = (t * 410) % 360
            sd.arc((5, 5, 35, 35), start=start, end=start + 275, fill=(38, 128, 210, 255), width=4)
            im.alpha_composite(spin, (int(mx) + 15, int(my) + 20))
        return im.convert("RGB")


class Camera:
    def __init__(self, width: int, height: int, seed: int):
        self.w, self.h = width, height
        self.rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        self.px, self.py = xx, yy
        self.xn = (xx - width / 2) / (width / 2)
        self.yn = (yy - height / 2) / (height / 2)
        self.r2 = self.xn * self.xn + self.yn * self.yn
        distortion = 1.0 + .018 * self.r2
        self.dx = (xx - width / 2) * distortion
        self.dy = (yy - height / 2) * distortion
        self.vignette = np.clip(1.025 - .105 * self.r2, .78, 1.0).astype(np.float32)
        reflection = (.020 * np.exp(-((self.xn + .58 + self.yn * .26) / .32) ** 2)
                      + .008 * np.exp(-((self.xn - .55 - self.yn * .4) / .55) ** 2))
        self.reflection = reflection[..., None] * np.array((.72, .84, 1.0), np.float32)
        self.fixed_noise = self.rng.normal(0, .0007, (height, width, 1)).astype(np.float32)
        self.ab_x = (xx + .32 * self.xn).astype(np.float32)
        self.ab_y = (yy + .32 * self.yn).astype(np.float32)

    def maps(self, t: float) -> tuple[np.ndarray, np.ndarray, float]:
        cx = 548 + 4.4 * math.sin(t * 1.37 + .4) + 1.5 * math.sin(t * 4.43) + .55 * math.sin(t * 11.3)
        cy = 359 + 3.5 * math.sin(t * 1.11 + 1.6) + 1.2 * math.sin(t * 5.17 + .5) + .45 * math.sin(t * 12.1)
        scale = 2.90 * (1 + .0045 * math.sin(t * .72) + .0015 * math.sin(t * 3.2))
        angle = math.radians(-.48 + .13 * math.sin(t * 1.24) + .035 * math.sin(t * 4.8))
        co, si = math.cos(angle), math.sin(angle)
        rx = co * self.dx - si * self.dy
        ry = si * self.dx + co * self.dy
        denom = 1 + .006 * self.xn - .004 * self.yn + .0007 * math.sin(t * .9)
        map_x = cx + rx / (scale * denom)
        map_y = cy + ry / (scale * denom)
        rolling = .055 * np.sin(self.yn * 7.0 + t * 2.1, dtype=np.float32)
        map_x = (map_x + rolling).astype(np.float32)
        map_y = map_y.astype(np.float32)
        return map_x, map_y, scale

    def render(self, screen: Image.Image, t: float) -> np.ndarray:
        source = np.asarray(screen, dtype=np.uint8)
        map_x, map_y, _ = self.maps(t)
        sampled = cv2.remap(source, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        frame = sampled.astype(np.float32) * (1.0 / 255.0)
        red = cv2.remap(frame[:, :, 0], self.ab_x, self.ab_y, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REFLECT)
        blue = cv2.remap(frame[:, :, 2], 2 * self.px - self.ab_x, 2 * self.py - self.ab_y,
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        frame[:, :, 0] = red
        frame[:, :, 2] = blue

        subpixel = np.mod(map_x, 1.0) * 3.0
        strength = .145
        for channel, center in enumerate((.5, 1.5, 2.5)):
            distance = np.abs(np.mod(subpixel - center + 1.5, 3.0) - 1.5)
            aperture = np.clip((.53 - distance) / .16, 0, 1)
            aperture = aperture * aperture * (3 - 2 * aperture)
            frame[:, :, channel] *= 1.0 - strength * (1.0 - aperture)
        vertical = np.mod(map_y, 1.0)
        edge = np.minimum(vertical, 1 - vertical)
        matrix = np.clip(edge / .075, 0, 1)
        frame *= (0.955 + .045 * matrix)[..., None]
        moire = 1 + .008 * np.sin(map_x * 2.13 + map_y * 1.71 + t * .23, dtype=np.float32)
        frame *= moire[..., None]

        frame *= self.vignette[..., None]
        frame += self.reflection + self.fixed_noise
        exposure = 1 + .005 * math.sin(t * .83 + .5)
        frame *= exposure
        frame = cv2.GaussianBlur(frame, (0, 0), .32)
        lum = self.rng.normal(0, .0030, (self.h, self.w, 1)).astype(np.float32)
        chroma = self.rng.normal(0, .0011, (self.h, self.w, 3)).astype(np.float32)
        frame += lum + chroma
        return np.uint8(np.clip(frame, 0, 1) * 255 + .5)


def make_audio(path: Path, duration: float, fps: int, seed: int) -> None:
    del fps
    rate = 48000
    count = int(duration * rate)
    rng = np.random.default_rng(seed + 99)
    audio = rng.normal(0, .00016, (count, 2)).astype(np.float32)
    for when in (2.02, 2.29):
        start = int(when * rate)
        n = int(.085 * rate)
        t = np.arange(n, dtype=np.float32) / rate
        click = (.036 * rng.normal(0, 1, n) * np.exp(-t * 145)
                 + .012 * np.sin(2 * np.pi * 1550 * t) * np.exp(-t * 90))
        end = min(count, start + n)
        audio[start:end, 0] += click[:end - start] * .92
        audio[start:end, 1] += click[:end - start]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def save_frame(rgb: np.ndarray, path: Path, quality: int) -> None:
    image = Image.fromarray(rgb)
    if path.suffix.lower() == ".png":
        image.save(path)
    else:
        image.save(path, quality=quality, subsampling=0)


def render(args: argparse.Namespace) -> None:
    duration = args.duration
    desktop = Desktop()
    camera = Camera(args.width, args.height, args.seed)
    if args.still:
        output = Path(args.still).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        rgb = camera.render(desktop.frame(args.at), args.at)
        Image.fromarray(rgb).save(output, quality=96, subsampling=0)
        print(f"Still saved: {output}")
        return

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = None
    if not args.no_frames:
        frames_dir = Path(args.frames_dir).resolve()
        frames_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output.with_suffix(".wav")
    make_audio(audio_path, duration, args.fps, args.seed)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.width}x{args.height}",
        "-r", str(args.fps), "-i", "-", "-i", str(audio_path),
        "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = int(round(duration * args.fps))
    try:
        for index in range(frames):
            t = index / args.fps
            rgb = camera.render(desktop.frame(t), t)
            if frames_dir is not None:
                name = f"frame_{index + 1:04d}.{args.frame_format}"
                save_frame(rgb, frames_dir / name, args.frame_quality)
            process.stdin.write(rgb.tobytes())
            if index % args.fps == 0 or index == frames - 1:
                print(f"Rendering {index + 1}/{frames} frames", flush=True)
    finally:
        if process.stdin:
            process.stdin.close()
    code = process.wait()
    if code:
        raise RuntimeError(f"ffmpeg exited with status {code}")
    audio_path.unlink(missing_ok=True)
    print(f"Video saved: {output}")
    if frames_dir is not None:
        print(f"Frames saved: {frames_dir} ({frames} images)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a realistic handheld macro video of a Chrome launch.")
    parser.add_argument("--output", default=str(ROOT / "files" / "chrome_screen_camera.mp4"))
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--seed", type=int, default=24)
    parser.add_argument("--crf", type=int, default=16)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--still", help="Render one JPEG instead of video")
    parser.add_argument("--at", type=float, default=4.8, help="Timeline position for --still")
    parser.add_argument("--frames-dir", default=str(ROOT / "images"),
                        help="Folder for every rendered frame (default: images/)")
    parser.add_argument("--frame-format", default="jpg", choices=["jpg", "png"],
                        help="Image format for saved frames (default: jpg)")
    parser.add_argument("--frame-quality", type=int, default=95,
                        help="JPEG quality for saved frames (default: 95)")
    parser.add_argument("--no-frames", action="store_true",
                        help="Only encode the video, skip saving single frames")
    args = parser.parse_args()
    if args.width < 320 or args.height < 180 or args.fps < 1 or args.duration <= 0:
        parser.error("Invalid video dimensions, frame rate, or duration")
    if not 1 <= args.frame_quality <= 100:
        parser.error("--frame-quality must be between 1 and 100")
    render(args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit("ffmpeg pipe closed unexpectedly")

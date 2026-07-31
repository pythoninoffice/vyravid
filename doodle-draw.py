#!/usr/bin/env python3
"""
Create a whiteboard doodle drawing animation from a still image.

Usage:
    python doodle-draw.py input.png output.mp4
    python doodle-draw.py input.png output.mp4 --duration 8 --speed slow --mode dots
"""

import argparse
import math
from pathlib import Path

import cairo
import cv2
import numpy as np

try:
    from moviepy.editor import VideoClip
except ImportError:
    from moviepy import VideoClip


def create_doodle_video(
    image_path: str,
    output_path: str,
    duration: float = 5.0,
    width: int | None = None,
    height: int | None = None,
    fps: int = 24,
    speed: str = "fast",
    color_fill_mode: str = "dots",
) -> Path:
    if speed not in {"fast", "slow"}:
        raise ValueError("speed must be 'fast' or 'slow'")
    if color_fill_mode not in {"dots", "path"}:
        raise ValueError("color_fill_mode must be 'dots' or 'path'")

    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image not found: {source}")

    img = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Could not load image: {source}")

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        # Composite transparent images onto white before edge detection.
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        bgr = img[:, :, :3].astype(np.float32)
        white = np.full_like(bgr, 255)
        img = (bgr * alpha + white * (1.0 - alpha)).astype(np.uint8)

    src_h, src_w = img.shape[:2]
    width = width or src_w
    height = height or src_h
    width += width % 2
    height += height % 2

    if speed == "slow":
        animation_duration = max(2.0, duration - 1.0)
        outline_duration = animation_duration / 2.0
        color_duration = animation_duration / 2.0
    else:
        outline_duration = duration / 4.0
        color_duration = duration / 4.0

    outline_brush = 8
    color_brush = 90

    scale = min(width / src_w, height / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    offset_x = (width - new_w) // 2
    offset_y = (height - new_h) // 2

    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)

    black_threshold = 200
    black_mask = gray < black_threshold
    img_black_only = np.ones_like(img_resized) * 255
    img_black_only[black_mask] = img_resized[black_mask]

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    paths = []
    total_path_length = 0.0
    for contour in contours:
        if cv2.arcLength(contour, False) < 50:
            continue

        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, False).reshape(-1, 2)
        if len(approx) < 2:
            continue

        points = [(int(x) + offset_x, int(y) + offset_y) for x, y in approx]
        path_length = sum(
            math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
            for i in range(1, len(points))
        )
        if path_length <= 0:
            continue

        paths.append({"points": points, "length": path_length})
        total_path_length += path_length

    paths.sort(key=lambda p: p["points"][0][1] + (p["points"][0][0] / 1000.0))

    full_black_surf = _image_to_full_surface(img_black_only, width, height, offset_x, offset_y)
    full_col_surf = _image_to_full_surface(img_resized, width, height, offset_x, offset_y)

    num_dots = 10000
    dot_radius = 10
    rng = np.random.default_rng(42)
    dots_x = rng.integers(0, width, num_dots)
    dots_y = rng.integers(0, height, num_dots)
    sorted_indices = np.argsort(dots_y + rng.uniform(-80, 80, num_dots))
    dots_x = dots_x[sorted_indices]
    dots_y = dots_y[sorted_indices]

    def draw_paths_to_mask(mask_ctx: cairo.Context, target_distance: float, line_width: int) -> None:
        mask_ctx.set_source_rgba(1, 1, 1, 1)
        mask_ctx.set_line_width(line_width)
        mask_ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        mask_ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        current_distance = 0.0
        for path in paths:
            points = path["points"]
            path_length = path["length"]
            if current_distance + path_length < target_distance:
                mask_ctx.move_to(*points[0])
                for point in points[1:]:
                    mask_ctx.line_to(*point)
                mask_ctx.stroke()
                current_distance += path_length
                continue

            if current_distance >= target_distance:
                break

            mask_ctx.move_to(*points[0])
            segment_distance = current_distance
            for i in range(1, len(points)):
                p1, p2 = points[i - 1], points[i]
                dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if segment_distance + dist >= target_distance:
                    ratio = (target_distance - segment_distance) / dist if dist > 0 else 0
                    mask_ctx.line_to(
                        p1[0] + (p2[0] - p1[0]) * ratio,
                        p1[1] + (p2[1] - p1[1]) * ratio,
                    )
                    break
                mask_ctx.line_to(*p2)
                segment_distance += dist
            mask_ctx.stroke()
            break

    def make_frame(t: float) -> np.ndarray:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()

        if t < outline_duration:
            progress = t / outline_duration if outline_duration else 1.0
            outline_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
            draw_paths_to_mask(
                cairo.Context(outline_mask),
                progress * total_path_length,
                outline_brush,
            )
            ctx.set_source_surface(full_black_surf, 0, 0)
            ctx.mask_surface(outline_mask, 0, 0)

        elif t < outline_duration + color_duration:
            outline_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
            draw_paths_to_mask(cairo.Context(outline_mask), total_path_length, outline_brush)
            ctx.set_source_surface(full_black_surf, 0, 0)
            ctx.mask_surface(outline_mask, 0, 0)

            progress = min((t - outline_duration) / color_duration, 1.0) if color_duration else 1.0
            color_mask = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
            color_ctx = cairo.Context(color_mask)
            color_ctx.set_source_rgba(1, 1, 1, 1)

            if color_fill_mode == "dots":
                for i in range(int(progress * num_dots)):
                    color_ctx.arc(int(dots_x[i]), int(dots_y[i]), dot_radius, 0, 2 * math.pi)
                    color_ctx.fill()
            else:
                draw_paths_to_mask(color_ctx, progress * total_path_length, color_brush)

            ctx.set_source_surface(full_col_surf, 0, 0)
            ctx.mask_surface(color_mask, 0, 0)

            if progress > 0.75:
                ctx.set_source_surface(full_col_surf, 0, 0)
                ctx.paint_with_alpha((progress - 0.75) / 0.25)

        else:
            ctx.set_source_surface(full_col_surf, 0, 0)
            ctx.paint()

        buf = surface.get_data()
        arr = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf)
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    video = VideoClip(make_frame, duration=duration)
    video.write_videofile(
        str(output),
        fps=fps,
        codec="libx264",
        preset="ultrafast",
        audio=False,
    )
    video.close()
    return output


def _image_to_full_surface(img_bgr: np.ndarray, width: int, height: int, x: int, y: int) -> cairo.ImageSurface:
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.uint8)
    img_rgbx = np.dstack([img_rgb, np.zeros(img_rgb.shape[:2], dtype=np.uint8)])
    img_bgrx = img_rgbx[:, :, [2, 1, 0, 3]].copy()
    h_img, w_img = img_bgr.shape[:2]
    small_surface = cairo.ImageSurface.create_for_data(
        img_bgrx.flatten(),
        cairo.FORMAT_RGB24,
        w_img,
        h_img,
        w_img * 4,
    )

    full_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(full_surface)
    ctx.set_source_surface(small_surface, x, y)
    ctx.paint()
    return full_surface


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a whiteboard doodle animation from an image.")
    parser.add_argument("image", help="Input image path")
    parser.add_argument("output", help="Output MP4 path")
    parser.add_argument("--duration", type=float, default=5.0, help="Video duration in seconds")
    parser.add_argument("--width", type=int, default=None, help="Output width. Defaults to source image width.")
    parser.add_argument("--height", type=int, default=None, help="Output height. Defaults to source image height.")
    parser.add_argument("--fps", type=int, default=24, help="Frames per second")
    parser.add_argument("--speed", choices=["fast", "slow"], default="fast", help="Animation speed")
    parser.add_argument("--mode", choices=["dots", "path"], default="dots", help="Color fill reveal mode")
    args = parser.parse_args()

    create_doodle_video(
        image_path=args.image,
        output_path=args.output,
        duration=args.duration,
        width=args.width,
        height=args.height,
        fps=args.fps,
        speed=args.speed,
        color_fill_mode=args.mode,
    )


if __name__ == "__main__":
    main()

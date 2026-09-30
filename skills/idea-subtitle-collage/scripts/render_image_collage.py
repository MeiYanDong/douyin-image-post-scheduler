#!/usr/bin/env python3
"""Turn a still image and ordered short lines into a native-style subtitle collage."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from collage_layout import DEFAULT_LABEL, render_collage


def parse_aspect(value: str) -> tuple[int, int]:
    try:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError
        aw, ah = map(int, parts)
        if aw <= 0 or ah <= 0 or not 1 <= ah / aw <= 2:
            raise ValueError
        return aw, ah
    except ValueError as exc:
        raise argparse.ArgumentTypeError("宽高比须为 3:4 等竖图比例") from exc


def normalize_lines(data: dict, default_image: Path, script_dir: Path):
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not 2 <= len(lines) <= 7:
        raise ValueError("lines 必须包含 2—7 句单行台词")
    texts, paths = [], []
    for number, line in enumerate(lines, 1):
        if isinstance(line, str):
            text, image = line, None
        elif isinstance(line, dict):
            if "t" in line:
                raise ValueError("静态图片模式不使用时间戳 t；直接按 lines 的顺序排版")
            text, image = line.get("text"), line.get("image")
        else:
            raise ValueError(f"第 {number} 句必须是文字或 text/image 对象")
        if not isinstance(text, str) or not text.strip() or "\n" in text or "\r" in text:
            raise ValueError(f"第 {number} 句必须是非空单行文字")
        if image is not None and (not isinstance(image, str) or not image.strip()):
            raise ValueError(f"第 {number} 句的 image 必须是非空路径")
        path = Path(image).expanduser() if image else default_image
        if image and not path.is_absolute():
            path = script_dir / path
        texts.append(text.strip())
        paths.append(path.resolve())
    return texts, paths


def validate_post(data: dict, directory: Path):
    if not re.match(r"^\d{3}_.+", directory.name):
        raise ValueError("素材目录须以三位编号开头，例如 001_我的想法")
    title, body, tags = data.get("title"), data.get("body"), data.get("tags")
    if (not isinstance(title, str) or not title.strip() or len(title.strip()) > 20
            or any(char in title for char in '/\\\n\r\0<>:"|?*')):
        raise ValueError("title 须为 1—20 字，不能包含路径字符或换行")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("导出素材包需要非空 body 正文")
    if not isinstance(tags, list) or len(tags) != 5 or any(
        not isinstance(tag, str) or not re.fullmatch(r"#[^\s#]+", tag) for tag in tags
    ) or len(set(tags)) != 5:
        raise ValueError("tags 须包含 5 个不同的 #话题")
    overhead = sum(len(tag) for tag in tags) + len(tags) * 4 + 10
    if len(body.strip()) + overhead > 1000:
        raise ValueError("正文加话题超过 1000 字预算；请先精简正文")
    return title.strip(), body.strip(), tags


def read_images(paths: list[Path]):
    images, sources = {}, []
    for path in dict.fromkeys(paths):
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            images[path] = ImageOps.exif_transpose(image).convert("RGB")
        sources.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                        "width": images[path].width, "height": images[path].height})
    return [images[path] for path in paths], sources


def save_image(image: Image.Image, path: Path):
    if path.suffix.lower() == ".png":
        image.save(path, format="PNG")
    elif path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, format="JPEG", quality=93, subsampling=0)
    else:
        raise ValueError("输出图片须使用 .jpg、.jpeg 或 .png")


def publish_files(staged: list[tuple[Path, Path]]):
    """Publish new files only; undo our own writes if a later exclusive write fails."""
    created = []
    try:
        for source, target in staged:
            with target.open("xb") as output:
                created.append(target)
                with source.open("rb") as source_file:
                    shutil.copyfileobj(source_file, output)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def build_parser():
    parser = argparse.ArgumentParser(description="静态图片＋短句 → 原生字幕拼图／抖音素材包")
    parser.add_argument("--image", type=Path, required=True, help="默认人物照片或无文字生图")
    parser.add_argument("--script", type=Path, required=True, help="包含有序 lines 的 UTF-8 JSON")
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", type=Path, help="图片输出路径，同时写入同名 JSON 清单")
    output.add_argument("--post-dir", type=Path, help="导出新的 001_内容名 素材目录")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--aspect", type=parse_aspect, default=(3, 4))
    parser.add_argument("--band-center", type=float, default=0.88)
    parser.add_argument("--hero-center", type=float, default=0.35,
                        help="主画面纵向裁切中心，默认偏上以保留人像头部")
    parser.add_argument("--hero-fraction", type=float)
    parser.add_argument("--font", help="支持中文的字体路径；未指定时自动检测系统字体")
    parser.add_argument("--font-size", type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        script_path = args.script.expanduser().resolve()
        data = json.loads(script_path.read_text(encoding="utf-8"))
        texts, paths = normalize_lines(data, args.image.expanduser().resolve(), script_path.parent)
        post_fields = None
        if args.post_dir:
            destination = args.post_dir.expanduser().resolve()
            post_fields = validate_post(data, destination)
            if destination.exists():
                raise ValueError(f"素材目录已存在，须使用新目录：{destination}")
        else:
            destination = args.out.expanduser().resolve()
            if destination.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                raise ValueError("输出图片须使用 .jpg、.jpeg 或 .png")
            if destination.exists() or destination.with_suffix(".json").exists():
                raise ValueError(f"输出已存在，须使用新文件名：{destination}")

        frames, sources = read_images(paths)
        canvas, layout = render_collage(
            frames, texts, width=args.width, aspect=args.aspect, band_center=args.band_center,
            hero_center=args.hero_center,
            hero_fraction=args.hero_fraction, font_path=args.font, font_size=args.font_size,
            label=data.get("label", DEFAULT_LABEL),
        )
        image_path = destination / "01_图片内容" / f"01_{post_fields[0]}.jpg" if post_fields else destination
        manifest = {"input_mode": "static_image", "script": str(script_path),
                    "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
                    "source_images": sources, "line_images": [str(path) for path in paths],
                    "claim_sources": data.get("sources", []), "layout": layout,
                    "output_image": str(image_path), "post_image_count": 1}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".collage-", dir=destination.parent) as temp:
            staging = Path(temp)
            if post_fields:
                package = staging / "post"
                pictures = package / "01_图片内容"
                pictures.mkdir(parents=True)
                staged_image = pictures / image_path.name
                save_image(canvas, staged_image)
                title, body, tags = post_fields
                for name, text in [("02_文字内容.txt", body), ("03_标题内容.txt", title),
                                   ("04_标签内容.txt", "\n".join(tags))]:
                    (package / name).write_text(text + "\n", encoding="utf-8")
                manifest["output_sha256"] = hashlib.sha256(staged_image.read_bytes()).hexdigest()
                (package / "05_生成清单.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                # Reserve the final directory exclusively before moving generated files.
                destination.mkdir()
                try:
                    for item in package.iterdir():
                        item.rename(destination / item.name)
                except BaseException:
                    shutil.rmtree(destination)
                    raise
            else:
                staged_image = staging / destination.name
                save_image(canvas, staged_image)
                manifest["output_sha256"] = hashlib.sha256(staged_image.read_bytes()).hexdigest()
                staged_manifest = staging / "manifest.json"
                staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
                publish_files([(staged_image, destination),
                               (staged_manifest, destination.with_suffix(".json"))])
        print(f"完成：{image_path} ({canvas.width}×{canvas.height})")
        print(f"主画面 {layout['hero_fraction']:.1%}，字幕条 {layout['strip_count']} 个，条间距 0")
        if post_fields:
            print("素材包已生成；队列预检请使用 prepare_queue.py --image-count 1")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

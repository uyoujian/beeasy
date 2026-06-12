#!/usr/bin/env python3
"""
PDF → 图片 → OCR 文字识别

将 PDF 拆解为单页图片，进行 OCR 文字识别。
支持两种识别方式:
  1. local — 使用本地 tesseract (默认, 推荐)
  2. pearocr — 通过 Playwright 自动化 PearOCR.com (实验性)

依赖:
  pip install Pillow pytesseract
  brew install tesseract ghostscript imagemagick tesseract-lang
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import json
import textwrap
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    from PIL import Image, ImageFilter, ImageEnhance
except ImportError:
    print("❌ 缺少 Pillow, 运行: pip install Pillow")
    sys.exit(1)


# ── 日志 ──

def log(msg: str, end="\n"):
    print(msg, end=end, file=sys.stderr, flush=True)


def status(text: str, dots: int = 0):
    if dots:
        log(f"\r{' ' * 60}\r{text}" + "." * dots, end="")
    else:
        log(f"\r{' ' * 60}\r{text}")


# ── 配置 ──

@dataclass
class OCRConfig:
    dpi: int = 200
    lang: str = "chi_sim+eng"
    method: str = "local"
    keep_images: bool = False
    output_format: str = "txt"
    preprocess: bool = True
    tesseract_cmd: str = "/opt/homebrew/bin/tesseract"
    tessdata_prefix: str = "/opt/homebrew/share/tessdata"


# ── 图片预处理 ──

def preprocess_image(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        img = img.convert("RGB")
    gray = img.convert("L")
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(1.5)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    bw = gray.point(lambda x: 255 if x > 128 else 0)
    return bw


# ── PDF 转换 ──

def check_tesseract(config: OCRConfig) -> bool:
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract
        return True
    except ImportError:
        return False


def get_pdf_images(pdf_path: str, output_dir: str, config: OCRConfig) -> list[str]:
    pdf_path = os.path.abspath(pdf_path)
    os.makedirs(output_dir, exist_ok=True)
    images = []

    if shutil.which("magick"):
        log("⏳ 转换 PDF → PNG (ImageMagick)...")
        pattern = os.path.join(output_dir, "page_%03d.png")
        t0 = time.time()
        result = subprocess.run(
            ["magick", "-density", str(config.dpi), pdf_path, "-quality", "90", pattern],
            capture_output=True, text=True, timeout=180
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            images = sorted(
                [os.path.join(output_dir, f) for f in os.listdir(output_dir)
                 if re.match(r"page_\d+\.png$", f)],
                key=lambda x: int(re.search(r"page_(\d+)", x).group(1))
            )
            log(f"  ✅ {len(images)} 页 ({elapsed:.1f}s)")

    if not images:
        log("❌ 无法转换 PDF。安装: brew install ghostscript imagemagick")
        sys.exit(1)

    return images


def split_tall_image(img_path: str, chunks_dir: str, max_height: int = 3000) -> list[str]:
    img = Image.open(img_path)
    w, h = img.size
    if h <= max_height:
        return [img_path]

    chunks = []
    base = os.path.splitext(os.path.basename(img_path))[0]
    for i in range(0, h, max_height):
        chunk = img.crop((0, i, w, min(i + max_height, h)))
        cp = os.path.join(chunks_dir, f"{base}_c{i//max_height:02d}.png")
        chunk.save(cp)
        chunks.append(cp)
    return chunks


def analyze_quality(text: str) -> dict:
    lines = text.strip().split("\n")
    total_chars = len(text)
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return {
        "total_chars": total_chars,
        "non_ascii_ratio": non_ascii / max(total_chars, 1),
        "line_count": len(lines),
    }


# ── OCR 引擎 ──

def ocr_local(image_paths: list[str], output_dir: str, config: OCRConfig) -> str:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
    os.environ["TESSDATA_PREFIX"] = config.tessdata_prefix

    chunks_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    pages = []
    total_pages = len(image_paths)
    total_chunks = 0
    t_start = time.time()

    for idx, img_path in enumerate(image_paths, 1):
        base = os.path.splitext(os.path.basename(img_path))[0]
        page_num = re.search(r"(\d+)", base)
        page_label = page_num.group(1) if page_num else base

        chunks = split_tall_image(img_path, chunks_dir, max_height=3000)
        if len(chunks) > 1:
            log(f"  ✂️  第{page_label}页 切{len(chunks)}段")
        total_chunks += len(chunks)

        page_lines = []
        for ci, cp in enumerate(chunks):
            try:
                img = Image.open(cp)
                if config.preprocess:
                    img = preprocess_image(img)
                else:
                    img = img.convert("RGB")

                text = pytesseract.image_to_string(img, lang=config.lang, config="--psm 6 --oem 3")
                if text.strip():
                    page_lines.append(text.strip())
            except Exception as e:
                log(f"  ⚠️  {os.path.basename(cp)}: {e}")

            chunk_label = f"[{ci+1}/{len(chunks)}]" if len(chunks) > 1 else ""
            elapsed = time.time() - t_start
            eta = elapsed / idx * total_pages - elapsed if idx > 0 else 0
            pct = idx / total_pages * 100
            log(f"\r  📄 第 {page_label} 页 {chunk_label} | "
                f"进度 {pct:.0f}% ({idx}/{total_pages}) | "
                f"耗时 {elapsed:.0f}s | 预估剩余 {eta:.0f}s{' ' * 10}", end="")

        pages.append(page_lines)
        char_count = sum(len(l) for l in page_lines)
        log(f"\r  ✅ 第 {page_label} 页 识别 {char_count} 字符{' ' * 40}")

    log("")

    # 写输出
    if config.output_format == "json":
        output_path = os.path.join(output_dir, "ocr_result.json")
        data = [
            {"page": i + 1, "text": "\n".join(lines), "char_count": sum(len(l) for l in lines)}
            for i, lines in enumerate(pages)
        ]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        md_lines = []
        for i, lines in enumerate(pages):
            if lines:
                md_lines.append(f"--- 第 {i+1} 页 ---\n" + "\n".join(lines))
        output_path = os.path.join(output_dir, "ocr_result.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(md_lines))

    quality = analyze_quality("\n".join(sum(pages, [])))
    t_total = time.time() - t_start
    log(f"📊 质量: {quality['total_chars']} 字符, "
        f"中文占比 {quality['non_ascii_ratio']:.0%}, "
        f"{quality['line_count']} 行")
    log(f"⏱  耗时: {t_total:.0f}s ({t_total/total_pages:.1f}s/页)")

    return output_path


def ocr_pearocr(image_paths: list[str], output_dir: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("❌ 需要: pip install playwright && playwright install chromium")
        sys.exit(1)

    output_path = os.path.join(output_dir, "ocr_result.txt")
    combined = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("https://pearocr.com", wait_until="networkidle")
        page.wait_for_timeout(3000)

        for i, img_path in enumerate(image_paths):
            log(f"  📄 上传第 {i+1}/{len(image_paths)} 张: {os.path.basename(img_path)}")
            page.goto("https://pearocr.com", wait_until="networkidle")
            page.wait_for_timeout(2000)

            file_input = page.query_selector('input[type="file"]')
            if file_input:
                file_input.set_input_files(img_path)
            else:
                drop = page.query_selector('[class*="drop"]')
                if drop:
                    drop.set_input_files(img_path)

            for s in range(30):
                status(f"⏳ 等待识别 ({s+1}s)")
                page.wait_for_timeout(1000)
                el = page.query_selector("textarea")
                if el:
                    t = (el.input_value() or "").strip()
                    if len(t) > 5:
                        text = t
                        break

            if text:
                combined.append(f"--- 第 {i+1} 张 ---\n{text}")
                log(f"\r  ✅ 第 {i+1} 张: {len(text)} 字符{' ' * 20}")
            else:
                log(f"\r  ⚠️ 第 {i+1} 张: 未识别到文字")

        browser.close()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(combined))

    return output_path


# ── 处理流程 ──

def process_single_pdf(pdf_path: str, output_dir: str, config: OCRConfig):
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, "images")

    log(f"\n{'=' * 50}")
    log(f"📄 {os.path.basename(pdf_path)}")
    log(f"{'=' * 50}")

    images = get_pdf_images(pdf_path, images_dir, config)

    if config.method == "pearocr":
        result = ocr_pearocr(images, output_dir)
    else:
        if not check_tesseract(config):
            log("⚠️  tesseract 不可用, 尝试 PearOCR...")
            result = ocr_pearocr(images, output_dir)
        else:
            result = ocr_local(images, output_dir, config)

    if not config.keep_images:
        for d in [images_dir, os.path.join(output_dir, "chunks")]:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)

    log(f"✅ 完成: {result}")
    return result


def process_batch(directory: str, output_dir: str, config: OCRConfig):
    pdfs = sorted(
        [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(".pdf")]
    )
    if not pdfs:
        log(f"❌ 目录中无 PDF: {directory}")
        sys.exit(1)

    log(f"\n📁 批量处理 {len(pdfs)} 个 PDF\n")

    results = []
    for pdf_path in pdfs:
        name = os.path.splitext(os.path.basename(pdf_path))[0]
        pdf_output = os.path.join(output_dir, name)
        result = process_single_pdf(pdf_path, pdf_output, config)
        results.append({"file": os.path.basename(pdf_path), "output": result})

    report = os.path.join(output_dir, "_batch_report.json")
    with open(report, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log(f"\n📊 批量报告: {report}")


# ── 主入口 ──

def main():
    parser = argparse.ArgumentParser(
        description="PDF/图片 → OCR 文字识别",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python3 pdf2ocr.py doc.pdf
              python3 pdf2ocr.py doc.pdf -o ./output --dpi 300
              python3 pdf2ocr.py doc.pdf --preprocess
              python3 pdf2ocr.py /path/to/pdfs/ --batch
              python3 pdf2ocr.py doc.pdf --output-format json
        """)
    )
    parser.add_argument("input", help="PDF 文件、图片目录 或 PDF 目录 (配合 --batch)")
    parser.add_argument("-o", "--output-dir", default="./ocr_output")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--method", default="local", choices=["local", "pearocr"])
    parser.add_argument("--lang", default="chi_sim+eng")
    parser.add_argument("--output-format", default="txt", choices=["txt", "json"])
    parser.add_argument("--preprocess", action="store_true", default=True)
    parser.add_argument("--no-preprocess", action="store_false", dest="preprocess")
    parser.add_argument("--keep-images", action="store_true")
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()

    config = OCRConfig(
        dpi=args.dpi, lang=args.lang, method=args.method,
        keep_images=args.keep_images, output_format=args.output_format,
        preprocess=args.preprocess,
    )

    output_dir = os.path.abspath(args.output_dir)
    input_path = args.input

    if os.path.isdir(input_path) and args.batch:
        process_batch(input_path, output_dir, config)
    elif os.path.isdir(input_path):
        images = sorted(
            [os.path.join(input_path, f) for f in os.listdir(input_path)
             if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))],
            key=lambda x: os.path.basename(x)
        )
        if not images:
            log(f"❌ 目录中无图片: {input_path}")
            sys.exit(1)
        log(f"📁 从目录加载 {len(images)} 张图片")
        os.makedirs(output_dir, exist_ok=True)
        if config.method == "pearocr":
            ocr_pearocr(images, output_dir)
        else:
            ocr_local(images, output_dir, config)
    else:
        if not os.path.exists(input_path):
            log(f"❌ 不存在: {input_path}")
            sys.exit(1)
        process_single_pdf(input_path, output_dir, config)


if __name__ == "__main__":
    main()

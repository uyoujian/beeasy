# Beeasy

PDF → OCR 文字识别工具。将不可选的 PDF 转为可复制的文本。

## 快速开始

```bash
pip install Pillow pytesseract
brew install tesseract ghostscript imagemagick tesseract-lang

python3 scripts/pdf2ocr.py input.pdf -o ./output
```

## 功能

- 本地 tesseract OCR（默认，快且可靠）
- PearOCR 浏览器自动化（实验性，需 chromium）
- 图片预处理（二值化/降噪/对比度增强）
- 实时进度显示（% / 耗时 / ETA）
- 批量处理目录
- JSON / TXT 双输出格式

详见 [SKILL.md](SKILL.md)。

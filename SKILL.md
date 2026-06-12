---
name: pdf-ocr-pearocr
description: PDF 拆页 + OCR 文字识别，支持本地 tesseract（默认）和 PearOCR 浏览器自动化两种模式。将不可选的 PDF 转为可复制的文本。
---

# PDF → OCR 文字识别

将 PDF 文档拆解为单页图片，自动 OCR 识别，合并输出为文本文件。支持**本地 tesseract**（快、可靠）和 **PearOCR**（浏览器端，需要 chromium）。

## 工作流程

```
PDF → magick/sips 拆页 → PNG → [预处理: 纠偏+二值化+降噪] → tesseract/PearOCR → 文本
```

## 前置条件

```bash
# 基础
brew install ghostscript imagemagick tesseract tesseract-lang
pip install Pillow pytesseract

# PearOCR 模式（额外）
pip install playwright
playwright install chromium
```

## 使用方法

```bash
# 基本用法（默认 local tesseract）
python3 scripts/pdf2ocr.py input.pdf -o ./ocr_output

# 高 DPI + 预处理（推荐扫描件）
python3 scripts/pdf2ocr.py input.pdf --dpi 300 --preprocess

# 批量处理目录下所有 PDF
python3 scripts/pdf2ocr.py /path/to/pdfs/ --batch

# JSON 格式输出（结构化）
python3 scripts/pdf2ocr.py input.pdf --output-format json

# 禁用预处理（极速模式）
python3 scripts/pdf2ocr.py input.pdf --no-preprocess
```

### 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `input` | PDF/图片目录/PDF目录(配合--batch) | — |
| `-o` | 输出目录 | `./ocr_output` |
| `--dpi` | 图片 DPI | `200` |
| `--method` | local / pearocr | `local` |
| `--lang` | 识别语言 | `chi_sim+eng` |
| `--preprocess` | 纠偏+二值化+降噪 | 开启 |
| `--no-preprocess` | 禁用预处理 | — |
| `--output-format` | txt / json | `txt` |
| `--keep-images` | 保留中间图片 | 不保留 |
| `--batch` | 批量模式 | 关闭 |

### 输出

| 文件 | 格式 | 说明 |
|------|------|------|
| `ocr_result.txt` | txt | 按页分隔的纯文本 |
| `ocr_result.json` | json | 结构化，含 page/char_count |
| `_batch_report.json` | json | 批量模式下的汇总 |
| `chunks/` | PNG | 切分后的图段（--keep-images） |

## 技术细节

- **PDF 拆页**: ImageMagick `magick`（依赖 ghostscript）
- **图片预处理**:
  - 灰度化 → 对比度增强 → 中值滤波降噪 → 二值化
  - 投影分析自动纠偏（-5° ~ +5°）
- **OCR 引擎（local）**: tesseract 5.5 + LSTM (OEM 3, PSM 6)
- **OCR 引擎（pearocr）**: PearOCR（Tesseract.js, 浏览器本地运算）
- **语言包**: `chi_sim` (中文简体) + `eng` (英文)

## 注意事项

- tesseract 中文语言包通过 `brew install tesseract-lang` 安装，若识别乱码请检查 symlink：
  ```bash
  ln -sf /opt/homebrew/Cellar/tesseract-lang/4.1.0/share/tessdata/*.traineddata \
         /opt/homebrew/share/tessdata/
  ```
- 预处理可显著提升中文扫描件识别质量，但耗时增加约 20-30%
- 识别质量取决于 PDF 清晰度，手写体/艺术字效果有限
- 输出文本建议再交给 Claude 做一次纠错（OCR 错别字校正）
- 大 PDF（50+ 页）建议分批或使用 `--batch`

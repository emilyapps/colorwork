# Colorwork Pattern Generator

A Python/Tkinter desktop app for designing symmetrical grid patterns for knitting and colorwork.

## Features

- Symmetry groups C1, D1, C2, D2, C4, D4 with rectangular grid support
- Click cells to toggle; Generate button for random fills
- Strip editor for repeat borders (width 0–7, with reflection options)
- Tiling preview with translation, reflection, and rotation repeats; brick offset
- Color picker with CMYK, HSL, hex input; gradient strip, contrast ratio, harmony swatches
- Save/load patterns and full projects (SQLite)
- Export to PDF (requires Ghostscript: `brew install ghostscript`)

## Requirements

- Python 3.9+
- Tkinter (included with most Python installs)
- Ghostscript for PDF export: `brew install ghostscript`

## Running

```
python3 pattern_generator.py
```

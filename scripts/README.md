# Image Optimization Tool (imgtool)

Production-ready CLI tool for batch image optimization with security enhancements and quality preservation.

## 🎯 Features

### Core Functionality
- **Format Conversion**: HEIC/HEIF, PNG, WebP, TIFF → optimized JPEG
- **Smart Compression**: Progressive JPEG with Huffman optimization
- **Automatic Organization**: Size-based bucketing (small/medium/large/xlarge)
- **Batch Processing**: Recursive directory scanning with structure preservation
- **Audit Reports**: CSV + JSON output for tracking all operations

### Security Enhancements (v2.0)
✅ **Path Traversal Protection**: Prevents malicious filenames from escaping output directory
✅ **Resource Limits**: Configurable max file size and image resolution
✅ **Quality Preservation**: Skips JPEG re-compression to prevent generation loss

### Advanced Options
- EXIF metadata preservation with orientation fix
- Configurable resize (e.g., max 1920px for web)
- Custom background colors for transparency
- Dry-run mode for safe previews
- Parallel processing support (future)

---

## 📦 Installation

### Requirements
```bash
# Core dependencies (required)
pip install Pillow

# Optional: HEIC/HEIF support (Mac/iPhone photos)
pip install pillow-heif

# Optional: Advanced EXIF manipulation
pip install piexif
```

### Quick Start
```bash
# Make script executable
chmod +x scripts/imgtool.py

# Basic usage
./scripts/imgtool.py /path/to/images

# Advanced usage
./scripts/imgtool.py ~/Photos -r --fix-orientation --preserve-exif -q 90
```

---

## 🚀 Usage Examples

### Basic Conversion
```bash
# Convert all images in a folder
python imgtool.py ./photos

# Output: ./cleaned/small/, ./cleaned/medium/, ./cleaned/large/, ./cleaned/xlarge/
```

### iPhone/Mac Photos (HEIC)
```bash
# Convert HEIC images with orientation fix
python imgtool.py ~/iPhone-Photos \
  --fix-orientation \
  --preserve-exif \
  -r
```

### Web Optimization
```bash
# Resize for web, high quality, recursive
python imgtool.py ./website-images \
  -r \
  --max-dim 1920 \
  -q 90 \
  --keep-structure
```

### Dry-Run Preview
```bash
# See what would happen without making changes
python imgtool.py ./images --dry-run -v
```

### PNG with Transparency
```bash
# Convert PNG with custom background color
python imgtool.py ./logos \
  --bg "#FF5733" \
  -o ./output-jpegs
```

---

## 🔒 Security Features

### 1. Path Traversal Protection
Prevents malicious filenames like `../../../etc/passwd.jpg` from escaping the output directory.

```python
# Automatic validation on all output paths
safe_output_path(base_dir="/output", target="../../etc/passwd")
# Raises: ValueError("Path traversal detected")
```

### 2. Resource Limits
Protects against memory exhaustion from oversized images.

```bash
# Custom limits
python imgtool.py ./images \
  --max-pixels 50000000 \    # ~50MP (7071x7071)
  --max-filesize-mb 100      # Skip files > 100MB
```

**Defaults:**
- Max pixels: 89,478,485 (~9k × 9k, Pillow's default)
- Max file size: 200 MB

### 3. JPEG Re-compression Prevention
Avoids quality loss from re-compressing existing JPEGs.

```bash
# Default: Skip existing JPEGs
python imgtool.py ./mixed-images
# Output: "Skipping JPEG: photo.jpg (already compressed)"

# Force re-compression (not recommended)
python imgtool.py ./mixed-images --force-recompress
```

---

## 📊 CLI Reference

### Required Arguments
| Argument | Description |
|----------|-------------|
| `input` | Input folder containing images |

### Output Options
| Flag | Default | Description |
|------|---------|-------------|
| `-o`, `--output` | `cleaned` | Output folder |
| `-r`, `--recursive` | Off | Recurse into subfolders |
| `--keep-structure` | Off | Mirror input directory structure under buckets |
| `--overwrite` | Off | Overwrite existing files |
| `--dry-run` | Off | Preview changes without writing |

### Quality Settings
| Flag | Default | Description |
|------|---------|-------------|
| `-q`, `--quality` | `85` | JPEG quality (1-100, recommended: 85-95) |
| `--bg` | `white` | Background for transparency (`white`, `black`, `#RRGGBB`) |

### Image Transformations
| Flag | Default | Description |
|------|---------|-------------|
| `--max-dim` | None | Resize longest side to max pixels (e.g., 1920) |
| `--fix-orientation` | Off | Apply EXIF orientation transpose |
| `--preserve-exif` | Off | Keep EXIF metadata (camera settings, GPS, etc.) |

### Security Options (New in v2.0)
| Flag | Default | Description |
|------|---------|-------------|
| `--force-recompress` | Off | Allow JPEG re-compression (quality loss) |
| `--max-pixels` | 89,478,485 | Maximum image resolution (~9k × 9k) |
| `--max-filesize-mb` | 200 | Skip files larger than this (MB) |

### Reporting & Logging
| Flag | Default | Description |
|------|---------|-------------|
| `--report` | `report` | Base name for CSV/JSON reports (empty to disable) |
| `-v`, `--verbose` | Off | Increase verbosity (`-v` = INFO, `-vv` = DEBUG) |
| `--log-file` | None | Write logs to file |

---

## 📁 Output Structure

### Default (Flat)
```
cleaned/
├── small/          # ≤ 200 KB
│   ├── photo1.jpg
│   └── photo2.jpg
├── medium/         # ≤ 600 KB
│   └── photo3.jpg
├── large/          # ≤ 1500 KB
│   └── photo4.jpg
└── xlarge/         # > 1500 KB
    └── photo5.jpg
```

### With `--keep-structure`
```
cleaned/
├── small/
│   └── 2024/
│       └── January/
│           └── photo1.jpg
├── medium/
│   └── 2024/
│       └── January/
│           └── photo2.jpg
...
```

---

## 📈 Reports

Generated automatically as `report.csv` and `report.json` in the output directory.

### CSV Example
```csv
src,dest,status,bucket,input_bytes,estimated_output_kb,output_bytes,converted_from,notes
/in/photo.heic,/out/small/photo.jpg,ok,small,2456789,156,159744,.heic,heif->jpg;exif_transpose;exif_preserve
/in/logo.png,/out/medium/logo.jpg,ok,medium,987654,432,442368,.png,png->jpg
/in/existing.jpg,,skipped,,,0,,.jpg,JPEG re-compression skipped
```

### Fields
- **src**: Original file path
- **dest**: Output file path
- **status**: `ok`, `skipped`, or `error`
- **bucket**: Size category
- **input_bytes**: Original file size
- **estimated_output_kb**: Predicted size
- **output_bytes**: Actual written size
- **converted_from**: Original format
- **notes**: Processing details

---

## 🔧 Advanced Configuration

### Size Buckets
Edit `SizeBucketsKB` in the script to customize thresholds:

```python
bucket_cfg = SizeBucketsKB(
    small_max=200,    # KB
    medium_max=600,   # KB
    large_max=1500    # KB
)
```

### Supported Formats
```python
SUPPORTED_INPUT_EXTS = {
    ".jpg", ".jpeg",  # Already compressed (skipped by default)
    ".png",           # Converted with background color
    ".webp",          # Modern web format
    ".tif", ".tiff",  # High-quality originals
    ".heic", ".heif"  # Apple formats (requires pillow-heif)
}
```

---

## ⚠️ Important Notes

### JPEG Re-compression
**By default, existing JPEG files are skipped** to prevent generation loss. Each JPEG re-encode degrades quality, even at high settings.

- ✅ **First-time conversion** (PNG/HEIC → JPEG): Full quality preserved
- ❌ **Re-compression** (JPEG → JPEG): Quality degradation
- 🔧 **Override**: Use `--force-recompress` only when necessary

### EXIF Orientation
When using `--fix-orientation`:
1. Image pixels are rotated correctly
2. Orientation tag is removed (requires `piexif`)
3. Prevents double-rotation in viewers

Without `piexif`, the orientation tag remains but is usually harmless.

### Memory Usage
Large batches may consume significant memory. Use resource limits:
```bash
# Process only smaller files
python imgtool.py ./huge-archive \
  --max-filesize-mb 50 \
  --max-pixels 25000000
```

---

## 🐛 Troubleshooting

### "HEIC/HEIF support missing"
```bash
pip install pillow-heif
```

### "Skipping JPEG" (unwanted)
```bash
# Force re-compression (reduces quality)
python imgtool.py ./images --force-recompress
```

### "Path traversal detected"
Input files have malicious names. This is a security feature. Check filenames:
```bash
find ./images -name "*../*"
```

### Out of memory
Reduce limits or process in smaller batches:
```bash
python imgtool.py ./images --max-pixels 50000000
```

---

## 📜 License

MIT License - See repository for details.

---

## 🤝 Contributing

Contributions welcome! Please test with `--dry-run` before submitting changes.

### Running Tests
```bash
# Dry-run test
python imgtool.py ./test-images --dry-run -vv

# Small batch test
python imgtool.py ./test-images -o ./test-output
```

---

## 📝 Changelog

### v2.0 (2026-01-17)
- ✅ Added path traversal protection (security)
- ✅ Added resource limits: max pixels, max file size (security)
- ✅ Added JPEG re-compression prevention (quality)
- ✅ Fixed CMYK color space handling
- ✅ Expanded quality range to 1-100
- ✅ Enhanced EXIF handling
- 📚 Comprehensive inline documentation

### v1.0
- Initial release with core functionality

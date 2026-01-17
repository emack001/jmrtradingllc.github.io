#!/usr/bin/env python3
"""
Image Optimization & Organization CLI

INTENT:
- Convert common image formats to web-friendly JPEG, compress, optionally resize,
  and organize outputs into size buckets.
- Best-effort preserve EXIF metadata (never error if missing/unneeded).
- Support Mac/iPhone HEIC/HEIF when pillow-heif is installed.
- Produce audit-friendly reports (CSV/JSON).
- Enhanced security: path traversal protection, resource limits, smart JPEG handling.

FEATURES:
- HEIC/HEIF -> JPEG (optional pillow-heif)
- PNG -> JPEG (handles transparency with chosen background color)
- Compress output JPEGs (quality, progressive, optimize)
- Optional resize by max dimension (e.g., 1920px)
- Optional EXIF orientation transpose (fix rotated images)
- Best-effort EXIF preservation; optionally strips Orientation tag if piexif installed
- Organize into size buckets (by output KB)
- CLI + logging + dry-run + optional reports
- Security: path traversal protection, resource limits
- Smart JPEG handling: avoid re-compression quality loss

SECURITY ENHANCEMENTS:
- Path traversal protection prevents malicious filenames from escaping output directory
- Resource limits prevent memory exhaustion from oversized images
- Input validation on all file operations

USAGE EXAMPLES:
  # Basic: Convert all images in a folder
  python imgtool.py /path/to/images

  # Advanced: Recursive with structure preservation, high quality, resize
  python imgtool.py /path/to/images -r --keep-structure -q 90 --max-dim 1920

  # HEIC from iPhone with orientation fix
  python imgtool.py ~/iPhone-Photos --fix-orientation --preserve-exif

  # Dry-run to preview changes
  python imgtool.py /path/to/images --dry-run -v
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional, Tuple, Dict, Any, List

from PIL import Image, ImageOps

# ============================================================================
# OPTIONAL DEPENDENCIES
# ============================================================================

# Optional: HEIC/HEIF support for Mac/iPhone images
# Install with: pip install pillow-heif
HEIF_ENABLED = False
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
    HEIF_ENABLED = True
except Exception:
    HEIF_ENABLED = False

# Optional: manipulate EXIF (strip Orientation after transpose)
# Install with: pip install piexif
PIEXIF_ENABLED = False
try:
    import piexif  # type: ignore
    PIEXIF_ENABLED = True
except Exception:
    PIEXIF_ENABLED = False


# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Supported input formats (extensible)
SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif"}

# Default resource limits (can be overridden via CLI)
DEFAULT_MAX_PIXELS = 89_478_485  # ~9k x 9k (Pillow's default limit)
DEFAULT_MAX_FILESIZE_MB = 200  # Skip files larger than this


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass(frozen=True)
class SizeBucketsKB:
    """
    INTENT:
    Define bucket thresholds in KB for output organization.

    Images are categorized into size buckets after processing:
    - small: <= small_max KB
    - medium: <= medium_max KB
    - large: <= large_max KB
    - xlarge: > large_max KB
    """
    small_max: int = 200
    medium_max: int = 600
    large_max: int = 1500


@dataclass
class ReportRow:
    """
    INTENT:
    Capture per-file processing outcomes for auditing and debugging.

    Each processed file generates a report row containing:
    - Input/output paths and sizes
    - Processing status and bucket assignment
    - Conversion details and notes
    """
    src: str
    dest: str
    status: str  # "ok", "skipped", "error"
    bucket: str  # "small", "medium", "large", "xlarge"
    input_bytes: int
    estimated_output_kb: int
    output_bytes: Optional[int]
    converted_from: str  # Original file extension
    notes: str = ""  # Processing details (e.g., "heif->jpg;exif_transpose")


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logger(verbosity: int, log_file: Optional[Path]) -> logging.Logger:
    """
    INTENT:
    Configure logging with appropriate verbosity level.

    Verbosity levels:
    - 0 (default): WARNING and above
    - 1 (-v): INFO and above
    - 2+ (-vv): DEBUG and above

    Args:
        verbosity: Number of -v flags passed
        log_file: Optional file path for log output

    Returns:
        Configured logger instance
    """
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logger = logging.getLogger("imgtool")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(level)
    logger.addHandler(ch)

    # Optional file handler
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(level)
        logger.addHandler(fh)

    return logger


# ============================================================================
# FILE DISCOVERY
# ============================================================================

def iter_images(input_dir: Path, recursive: bool) -> Iterable[Path]:
    """
    INTENT:
    Discover all supported image files in input directory.

    Args:
        input_dir: Directory to search
        recursive: Whether to search subdirectories

    Yields:
        Path objects for each supported image file
    """
    if recursive:
        for p in input_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS:
                yield p
    else:
        for p in input_dir.iterdir():
            if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS:
                yield p


# ============================================================================
# SECURITY: PATH TRAVERSAL PROTECTION (OPTION 1)
# ============================================================================

def safe_output_path(base_dir: Path, relative_path: Path) -> Path:
    """
    INTENT:
    Prevent path traversal attacks by validating output paths.

    Security consideration:
    Malicious filenames like "../../../etc/passwd.jpg" could escape
    the output directory. This function ensures all output paths
    resolve within the intended base directory.

    Args:
        base_dir: The root output directory (e.g., /output/cleaned)
        relative_path: The target path (e.g., bucket/image.jpg)

    Returns:
        Validated absolute path within base_dir

    Raises:
        ValueError: If the resolved path escapes base_dir

    Example:
        >>> safe_output_path(Path("/output"), Path("../../../etc/passwd"))
        ValueError: Path traversal detected

        >>> safe_output_path(Path("/output"), Path("images/photo.jpg"))
        PosixPath('/output/images/photo.jpg')
    """
    # Resolve to absolute path and check containment
    base_resolved = base_dir.resolve()
    target_resolved = (base_dir / relative_path).resolve()

    # Ensure the target is within base directory
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(
            f"Security: Path traversal detected. "
            f"Target '{relative_path}' would escape base directory '{base_dir}'"
        )

    return target_resolved


# ============================================================================
# RESOURCE LIMITS (OPTION 2)
# ============================================================================

def check_file_size_limit(path: Path, max_mb: int, logger: logging.Logger) -> bool:
    """
    INTENT:
    Skip files exceeding size limit to prevent memory exhaustion.

    Large files can cause memory issues during processing. This check
    protects against accidental processing of huge files.

    Args:
        path: File to check
        max_mb: Maximum allowed file size in megabytes
        logger: Logger instance

    Returns:
        True if file is within limits, False if too large
    """
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            logger.warning(
                "Skipping %s: file size %.1f MB exceeds limit of %d MB",
                path, size_mb, max_mb
            )
            return False
        return True
    except Exception as e:
        logger.warning("Could not check file size for %s: %s", path, e)
        return True  # Allow processing if we can't check size


def check_image_resolution_limit(img: Image.Image, max_pixels: int, logger: logging.Logger) -> bool:
    """
    INTENT:
    Validate image resolution to prevent memory exhaustion.

    Very high resolution images (e.g., 20000x20000 pixels) can consume
    excessive memory. Pillow has a default decompression bomb limit
    of ~89MP, but we allow custom limits.

    Args:
        img: PIL Image object
        max_pixels: Maximum allowed total pixels
        logger: Logger instance

    Returns:
        True if image is within limits, False if too large
    """
    width, height = img.size
    total_pixels = width * height

    if total_pixels > max_pixels:
        logger.warning(
            "Skipping image: resolution %dx%d (%d pixels) exceeds limit of %d pixels",
            width, height, total_pixels, max_pixels
        )
        return False

    return True


# ============================================================================
# ARGUMENT PARSING HELPERS
# ============================================================================

def parse_bg_color(s: str) -> Tuple[int, int, int]:
    """
    INTENT:
    Parse background color from user input.

    Supports:
    - Named colors: "white", "black"
    - Hex colors: "#FFFFFF", "#000000"

    Args:
        s: Color string

    Returns:
        RGB tuple (0-255, 0-255, 0-255)

    Raises:
        argparse.ArgumentTypeError: If color format is invalid
    """
    s = s.strip().lower()
    if s == "white":
        return (255, 255, 255)
    if s == "black":
        return (0, 0, 0)

    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        raise argparse.ArgumentTypeError(
            "bg must be 'white', 'black', or 6-digit hex like #ffffff"
        )

    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Invalid hex color for bg. Example: #ffffff"
        ) from None


# ============================================================================
# IMAGE LOADING
# ============================================================================

def safe_open_image(path: Path, logger: logging.Logger) -> Optional[Image.Image]:
    """
    INTENT:
    Safely open image with format-specific error handling.

    Handles:
    - HEIC/HEIF files when pillow-heif is not installed
    - Corrupted or unsupported files
    - Pillow exceptions

    Args:
        path: Path to image file
        logger: Logger instance

    Returns:
        PIL Image object if successful, None if failed
    """
    ext = path.suffix.lower()

    # Check for HEIC/HEIF support
    if ext in (".heic", ".heif") and not HEIF_ENABLED:
        logger.warning(
            "Skipping %s (HEIC/HEIF support missing; install pillow-heif).", path
        )
        return None

    try:
        return Image.open(path)
    except Exception as e:
        logger.warning("Failed to open %s: %s", path, e)
        return None


# ============================================================================
# JPEG RE-COMPRESSION PREVENTION (OPTION 3)
# ============================================================================

def should_skip_jpeg_recompression(
    path: Path,
    force_recompress: bool,
    logger: logging.Logger
) -> bool:
    """
    INTENT:
    Prevent quality loss from re-compressing existing JPEGs.

    Re-compressing JPEG files introduces generation loss (quality degradation)
    due to the lossy nature of JPEG compression. Each re-encode loses
    more detail, even at high quality settings.

    This function skips JPEG inputs unless --force-recompress is explicitly set.

    Args:
        path: Input file path
        force_recompress: Whether user explicitly allows re-compression
        logger: Logger instance

    Returns:
        True if file should be skipped, False if it should be processed

    Example:
        Input: photo.jpg at 90% quality
        Without --force-recompress: SKIPPED (preserves original quality)
        With --force-recompress: PROCESSED (user accepts quality loss)
    """
    if path.suffix.lower() in (".jpg", ".jpeg"):
        if not force_recompress:
            logger.info(
                "Skipping JPEG: %s (already compressed; use --force-recompress to override)",
                path
            )
            return True
    return False


# ============================================================================
# COLOR SPACE CONVERSION
# ============================================================================

def ensure_rgb_for_jpeg(img: Image.Image, bg_rgb: Tuple[int, int, int]) -> Image.Image:
    """
    INTENT:
    Convert images to RGB suitable for JPEG output.

    JPEG format only supports RGB color space. This function handles:
    - RGBA/LA: Composite alpha channel against solid background
    - Palette mode (P): Convert and composite if transparent
    - CMYK: Convert to RGB (common in print-quality images)
    - Grayscale/other: Convert to RGB

    Args:
        img: PIL Image in any color mode
        bg_rgb: Background color for alpha compositing (R, G, B)

    Returns:
        PIL Image in RGB mode suitable for JPEG

    Note:
        Alpha compositing uses the background color to replace
        transparent areas. Default is white (255, 255, 255).
    """
    # Handle images with alpha channel
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, bg_rgb)
        bg.paste(img, mask=img.split()[-1])  # Use alpha as mask
        return bg

    # Handle palette mode (may have transparency)
    if img.mode == "P":
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, bg_rgb)
        bg.paste(img, mask=img.split()[-1])
        return bg

    # Handle CMYK (common in professional photography)
    if img.mode == "CMYK":
        return img.convert("RGB")

    # Handle other modes (L, LAB, etc.)
    if img.mode != "RGB":
        return img.convert("RGB")

    return img


# ============================================================================
# IMAGE TRANSFORMATIONS
# ============================================================================

def resize_max_dim(img: Image.Image, max_dim: Optional[int]) -> Image.Image:
    """
    INTENT:
    Optionally resize image so its largest dimension <= max_dim.

    Maintains aspect ratio. Useful for:
    - Web optimization (e.g., max 1920px for full HD displays)
    - Mobile optimization (e.g., max 1024px)
    - Thumbnail generation (e.g., max 256px)

    Args:
        img: PIL Image to resize
        max_dim: Maximum dimension in pixels (None to skip resize)

    Returns:
        Resized image or original if already within limit

    Example:
        Input: 4000x3000 image, max_dim=1920
        Output: 1920x1440 image (maintains 4:3 aspect ratio)
    """
    if not max_dim:
        return img

    w, h = img.size
    longest = max(w, h)

    # Skip resize if already within limit
    if longest <= max_dim:
        return img

    # Calculate new dimensions maintaining aspect ratio
    scale = max_dim / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    # Use LANCZOS for high-quality downsampling
    return img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)


# ============================================================================
# EXIF METADATA HANDLING
# ============================================================================

def best_effort_exif_bytes(img: Image.Image) -> Optional[bytes]:
    """
    INTENT:
    Extract EXIF bytes if present; otherwise return None.

    Never throws exceptions. EXIF data contains:
    - Camera settings (ISO, aperture, shutter speed)
    - Capture date/time
    - GPS coordinates (if enabled)
    - Orientation flag

    Args:
        img: PIL Image object

    Returns:
        EXIF bytes if available, None otherwise

    Note:
        Some formats (PNG, WebP) may not have EXIF data.
        This is not an error condition.
    """
    try:
        # Pillow stores raw EXIF bytes in info dict
        exif = img.info.get("exif")
        if exif:
            return exif
    except Exception:
        pass
    return None


def strip_orientation_if_possible(exif_bytes: Optional[bytes]) -> Optional[bytes]:
    """
    INTENT:
    Remove EXIF Orientation tag after applying transpose.

    When we apply EXIF orientation (rotate the image pixels),
    we must remove the Orientation tag to prevent double-rotation
    when viewed in EXIF-aware software.

    Requires piexif library. Fails gracefully if not available.

    Args:
        exif_bytes: Raw EXIF data

    Returns:
        Modified EXIF bytes with Orientation removed, or original on failure

    Technical note:
        EXIF Orientation tag is ID 274 (0x0112) in IFD0.
        Values 1-8 indicate rotation/flip transformations.
    """
    if not exif_bytes or not PIEXIF_ENABLED:
        return exif_bytes

    try:
        data = piexif.load(exif_bytes)
        # Remove Orientation tag (274) from 0th IFD
        if "0th" in data and piexif.ImageIFD.Orientation in data["0th"]:
            data["0th"].pop(piexif.ImageIFD.Orientation, None)
        return piexif.dump(data)
    except Exception:
        # Return original bytes if manipulation fails
        return exif_bytes


# ============================================================================
# SIZE ESTIMATION & BUCKETING
# ============================================================================

def estimate_jpeg_size_kb(
    img: Image.Image,
    quality: int,
    exif_bytes: Optional[bytes]
) -> int:
    """
    INTENT:
    Estimate output JPEG file size without writing to disk.

    Used for bucket assignment before saving. Saves to in-memory
    buffer to get accurate size prediction.

    Args:
        img: RGB PIL Image ready for JPEG encoding
        quality: JPEG quality (1-100)
        exif_bytes: Optional EXIF data to include

    Returns:
        Estimated file size in kilobytes (minimum 1 KB)
    """
    import io

    buf = io.BytesIO()
    save_kwargs = dict(
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True
    )
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes

    img.save(buf, **save_kwargs)
    return max(1, len(buf.getvalue()) // 1024)


def compute_bucket(kb: int, buckets: SizeBucketsKB) -> str:
    """
    INTENT:
    Assign output file to size bucket based on file size.

    Bucket categories:
    - small: Quick-loading thumbnails/icons
    - medium: Standard web images
    - large: High-quality hero images
    - xlarge: Full-resolution originals

    Args:
        kb: File size in kilobytes
        buckets: Bucket threshold configuration

    Returns:
        Bucket name: "small", "medium", "large", or "xlarge"
    """
    if kb <= buckets.small_max:
        return "small"
    if kb <= buckets.medium_max:
        return "medium"
    if kb <= buckets.large_max:
        return "large"
    return "xlarge"


# ============================================================================
# FILE OPERATIONS
# ============================================================================

def unique_path(dest: Path) -> Path:
    """
    INTENT:
    Generate unique filename to prevent overwrites.

    If destination exists, appends _1, _2, _3, etc.

    Args:
        dest: Desired destination path

    Returns:
        Unique path that doesn't exist

    Example:
        photo.jpg -> photo.jpg (if available)
        photo.jpg -> photo_1.jpg (if photo.jpg exists)
        photo.jpg -> photo_2.jpg (if photo_1.jpg exists)
    """
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    i = 1
    while True:
        candidate = dest.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def save_as_jpeg(
    img: Image.Image,
    dest: Path,
    quality: int,
    exif_bytes: Optional[bytes],
    dry_run: bool,
    logger: logging.Logger,
) -> Optional[int]:
    """
    INTENT:
    Save image as optimized JPEG with specified quality.

    JPEG optimization features:
    - Progressive encoding (loads incrementally in browsers)
    - Huffman table optimization (better compression)
    - Optional EXIF metadata preservation

    Args:
        img: RGB PIL Image ready for encoding
        dest: Output file path (must be within safe directory)
        quality: JPEG quality 1-100 (85-95 recommended)
        exif_bytes: Optional EXIF metadata
        dry_run: If True, don't actually write file
        logger: Logger instance

    Returns:
        File size in bytes if written, None if dry-run
    """
    if dry_run:
        logger.info("[DRY-RUN] Would write: %s", dest)
        return None

    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Configure JPEG encoding
    save_kwargs = dict(
        format="JPEG",
        quality=quality,
        optimize=True,      # Optimize Huffman tables
        progressive=True    # Progressive encoding for web
    )
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes

    # Write file
    img.save(dest, **save_kwargs)
    return dest.stat().st_size


# ============================================================================
# REPORTING
# ============================================================================

def write_reports(
    out_dir: Path,
    rows: List[ReportRow],
    report_base: Optional[str],
    logger: logging.Logger,
    dry_run: bool,
) -> None:
    """
    INTENT:
    Generate CSV and JSON audit reports.

    Reports contain:
    - Processing status for each file
    - Input/output sizes and paths
    - Conversion details and notes

    Useful for:
    - Auditing batch operations
    - Debugging processing failures
    - Analyzing compression ratios

    Args:
        out_dir: Output directory for report files
        rows: List of processing results
        report_base: Base filename (e.g., "report" -> report.csv, report.json)
        logger: Logger instance
        dry_run: If True, don't write reports
    """
    if not report_base:
        return

    csv_path = out_dir / f"{report_base}.csv"
    json_path = out_dir / f"{report_base}.json"

    if dry_run:
        logger.info("[DRY-RUN] Would write report CSV: %s", csv_path)
        logger.info("[DRY-RUN] Would write report JSON: %s", json_path)
        return

    # Write CSV report
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(asdict(rows[0]).keys()) if rows else [
            "src", "dest", "status", "bucket", "input_bytes",
            "estimated_output_kb", "output_bytes", "converted_from", "notes"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))

    # Write JSON report
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in rows], f, indent=2)

    logger.info("Wrote reports: %s and %s", csv_path, json_path)


# ============================================================================
# CORE PROCESSING FUNCTION
# ============================================================================

def process_one(
    src: Path,
    out_dir: Path,
    rel_root: Path,
    buckets: SizeBucketsKB,
    quality: int,
    bg_rgb: Tuple[int, int, int],
    keep_structure: bool,
    overwrite: bool,
    dry_run: bool,
    logger: logging.Logger,
    fix_orientation: bool,
    preserve_exif: bool,
    max_dim: Optional[int],
    force_recompress: bool,
    max_pixels: int,
    max_filesize_mb: int,
) -> ReportRow:
    """
    INTENT:
    Process a single image file through the optimization pipeline.

    Processing steps:
    1. Validate file size (skip if too large)
    2. Check for JPEG re-compression (skip unless forced)
    3. Open and validate image
    4. Check resolution limits
    5. Extract EXIF metadata (optional)
    6. Fix orientation (optional)
    7. Resize to max dimension (optional)
    8. Convert to RGB for JPEG
    9. Estimate output size and assign bucket
    10. Save optimized JPEG

    Args:
        src: Source image path
        out_dir: Base output directory
        rel_root: Root for relative path calculation
        buckets: Size bucket configuration
        quality: JPEG quality (1-100)
        bg_rgb: Background color for alpha compositing
        keep_structure: Mirror input directory structure
        overwrite: Overwrite existing files
        dry_run: Preview mode (don't write files)
        logger: Logger instance
        fix_orientation: Apply EXIF orientation transpose
        preserve_exif: Keep EXIF metadata
        max_dim: Maximum dimension for resize
        force_recompress: Allow JPEG re-compression
        max_pixels: Maximum image resolution
        max_filesize_mb: Maximum input file size

    Returns:
        ReportRow with processing results
    """
    input_bytes = 0
    try:
        input_bytes = src.stat().st_size
    except Exception:
        pass

    # SECURITY: Check file size limit (Option 2)
    if not check_file_size_limit(src, max_filesize_mb, logger):
        return ReportRow(
            src=str(src),
            dest="",
            status="skipped",
            bucket="",
            input_bytes=input_bytes,
            estimated_output_kb=0,
            output_bytes=None,
            converted_from=src.suffix.lower(),
            notes=f"File size exceeds {max_filesize_mb}MB limit",
        )

    # QUALITY PRESERVATION: Skip JPEG re-compression (Option 3)
    if should_skip_jpeg_recompression(src, force_recompress, logger):
        return ReportRow(
            src=str(src),
            dest="",
            status="skipped",
            bucket="",
            input_bytes=input_bytes,
            estimated_output_kb=0,
            output_bytes=None,
            converted_from=src.suffix.lower(),
            notes="JPEG re-compression skipped (use --force-recompress to override)",
        )

    # Open image with error handling
    img = safe_open_image(src, logger)
    if img is None:
        return ReportRow(
            src=str(src),
            dest="",
            status="skipped",
            bucket="",
            input_bytes=input_bytes,
            estimated_output_kb=0,
            output_bytes=None,
            converted_from=src.suffix.lower(),
            notes="Unsupported format or failed to open",
        )

    try:
        with img:
            # Load image data
            img.load()

            # SECURITY: Check resolution limit (Option 2)
            if not check_image_resolution_limit(img, max_pixels, logger):
                return ReportRow(
                    src=str(src),
                    dest="",
                    status="skipped",
                    bucket="",
                    input_bytes=input_bytes,
                    estimated_output_kb=0,
                    output_bytes=None,
                    converted_from=src.suffix.lower(),
                    notes=f"Resolution exceeds {max_pixels} pixels limit",
                )

            # Best-effort EXIF capture (optional)
            exif_bytes = best_effort_exif_bytes(img) if preserve_exif else None

            # Optional: fix orientation for correct visual output
            # If we transpose, we *try* to strip Orientation tag to avoid double-rotation.
            if fix_orientation:
                img = ImageOps.exif_transpose(img)
                if preserve_exif:
                    exif_bytes = strip_orientation_if_possible(exif_bytes)

            # Optional resize, then RGB conversion for JPEG
            img = resize_max_dim(img, max_dim=max_dim)
            rgb = ensure_rgb_for_jpeg(img, bg_rgb)

            # Estimate output size for bucketing
            est_kb = estimate_jpeg_size_kb(rgb, quality=quality, exif_bytes=exif_bytes)
            bucket = compute_bucket(est_kb, buckets)

            # Build destination path
            rel = src.relative_to(rel_root) if keep_structure else None
            if keep_structure and rel is not None:
                # Mirror directory structure under bucket
                relative_dest = bucket / rel.parent / (src.stem + ".jpg")
            else:
                # Flat structure under bucket
                relative_dest = Path(bucket) / (src.stem + ".jpg")

            # SECURITY: Validate output path (Option 1)
            try:
                dest = safe_output_path(out_dir, relative_dest)
            except ValueError as e:
                logger.error("Path traversal detected for %s: %s", src, e)
                return ReportRow(
                    src=str(src),
                    dest="",
                    status="error",
                    bucket="",
                    input_bytes=input_bytes,
                    estimated_output_kb=0,
                    output_bytes=None,
                    converted_from=src.suffix.lower(),
                    notes=f"Security: {e}",
                )

            # Ensure unique filename if not overwriting
            if not overwrite:
                dest = unique_path(dest)

            logger.info(
                "IN: %s | OUT: %s | bucket=%s | est=%dKB",
                src, dest, bucket, est_kb
            )

            # Save optimized JPEG
            out_bytes = save_as_jpeg(
                rgb, dest, quality=quality, exif_bytes=exif_bytes,
                dry_run=dry_run, logger=logger
            )

            # Build processing notes
            notes = []
            if src.suffix.lower() in (".heic", ".heif") and HEIF_ENABLED:
                notes.append("heif->jpg")
            if src.suffix.lower() == ".png":
                notes.append("png->jpg")
            if max_dim:
                notes.append(f"max_dim={max_dim}")
            if fix_orientation:
                notes.append("exif_transpose")
            if preserve_exif:
                notes.append("exif_preserve" if exif_bytes else "exif_missing")

            return ReportRow(
                src=str(src),
                dest=str(dest),
                status="ok",
                bucket=bucket,
                input_bytes=input_bytes,
                estimated_output_kb=est_kb,
                output_bytes=out_bytes,
                converted_from=src.suffix.lower(),
                notes=";".join(notes),
            )

    except Exception as e:
        logger.warning("Failed processing %s: %s", src, e)
        return ReportRow(
            src=str(src),
            dest="",
            status="error",
            bucket="",
            input_bytes=input_bytes,
            estimated_output_kb=0,
            output_bytes=None,
            converted_from=src.suffix.lower(),
            notes=str(e),
        )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main() -> int:
    """
    INTENT:
    Main CLI entry point with argument parsing and batch processing.

    Returns:
        Exit code (0 = success, non-zero = error)
    """
    parser = argparse.ArgumentParser(
        prog="imgtool",
        description=(
            "Convert/compress images to JPEG, organize by size buckets, "
            "and generate reports. Enhanced with security features and "
            "smart JPEG handling to prevent quality loss."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s ./photos -r -v\n"
            "  %(prog)s ./iphone-pics --fix-orientation --preserve-exif\n"
            "  %(prog)s ./images -q 90 --max-dim 1920 --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        "input",
        type=Path,
        help="Input folder containing images"
    )

    # Output configuration
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("cleaned"),
        help="Output folder (default: cleaned)"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recurse into subfolders"
    )
    parser.add_argument(
        "--keep-structure",
        action="store_true",
        help="Mirror input folder structure under each bucket"
    )

    # Quality settings
    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=85,
        help="JPEG quality (1-100). Recommended: 85-95. Default: 85"
    )
    parser.add_argument(
        "--bg",
        type=parse_bg_color,
        default=parse_bg_color("white"),
        help="Background for transparency: white|black|#RRGGBB (default: white)"
    )

    # File handling
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output files if they already exist"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files"
    )

    # Image transformations
    parser.add_argument(
        "--max-dim",
        type=int,
        default=None,
        help="Optional: resize so the longest side <= this value (e.g., 1920)."
    )
    parser.add_argument(
        "--fix-orientation",
        action="store_true",
        help="Optional: apply EXIF orientation transpose for correct rotation."
    )
    parser.add_argument(
        "--preserve-exif",
        action="store_true",
        help="Best-effort: preserve EXIF when present (never errors if missing)."
    )

    # OPTION 3: JPEG Re-compression Control
    parser.add_argument(
        "--force-recompress",
        action="store_true",
        help=(
            "Allow re-compression of existing JPEG files (may reduce quality). "
            "By default, JPEGs are skipped to prevent generation loss."
        )
    )

    # OPTION 2: Resource Limits
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=DEFAULT_MAX_PIXELS,
        help=(
            f"Maximum image resolution in pixels (default: {DEFAULT_MAX_PIXELS:,}, ~9k x 9k). "
            "Prevents memory exhaustion from oversized images."
        )
    )
    parser.add_argument(
        "--max-filesize-mb",
        type=int,
        default=DEFAULT_MAX_FILESIZE_MB,
        help=(
            f"Skip input files larger than this in MB (default: {DEFAULT_MAX_FILESIZE_MB}). "
            "Prevents processing of unexpectedly large files."
        )
    )

    # Reporting
    parser.add_argument(
        "--report",
        type=str,
        default="report",
        help=(
            "Write CSV+JSON report files using this base name (default: report). "
            "Use '' to disable reports."
        )
    )

    # Logging
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional log file path"
    )

    args = parser.parse_args()
    logger = setup_logger(args.verbose, args.log_file)

    # Validate inputs
    input_dir: Path = args.input
    out_dir: Path = args.output

    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("Input must be a directory: %s", input_dir)
        return 2

    if args.quality < 1 or args.quality > 100:
        logger.error("Quality must be between 1 and 100.")
        return 2

    # Log dependency status
    if not HEIF_ENABLED:
        logger.info(
            "HEIC/HEIF support is OFF (install pillow-heif to enable: pip install pillow-heif)."
        )
    else:
        logger.info("HEIC/HEIF support is enabled.")

    if args.fix_orientation and args.preserve_exif and not PIEXIF_ENABLED:
        logger.info(
            "piexif not installed; Orientation tag may remain in EXIF after transpose "
            "(install with: pip install piexif). This is not an error."
        )

    # Configure size buckets
    bucket_cfg = SizeBucketsKB(small_max=200, medium_max=600, large_max=1500)

    # Discover images
    images = list(iter_images(input_dir, recursive=args.recursive))
    if not images:
        logger.warning("No supported image files found in %s", input_dir)
        return 0

    logger.info("Found %d image(s). Processing with quality=%d...", len(images), args.quality)

    # Process each image
    rows: List[ReportRow] = []
    report_base = args.report.strip() if isinstance(args.report, str) else None
    if report_base == "":
        report_base = None

    for src in images:
        row = process_one(
            src=src,
            out_dir=out_dir,
            rel_root=input_dir,
            buckets=bucket_cfg,
            quality=args.quality,
            bg_rgb=args.bg,
            keep_structure=args.keep_structure,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            logger=logger,
            fix_orientation=args.fix_orientation,
            preserve_exif=args.preserve_exif,
            max_dim=args.max_dim,
            force_recompress=args.force_recompress,
            max_pixels=args.max_pixels,
            max_filesize_mb=args.max_filesize_mb,
        )
        rows.append(row)

    # Generate reports
    write_reports(out_dir, rows, report_base, logger, args.dry_run)

    # Summary statistics
    ok_count = sum(1 for r in rows if r.status == "ok")
    skipped_count = sum(1 for r in rows if r.status == "skipped")
    error_count = sum(1 for r in rows if r.status == "error")

    logger.info(
        "Done. Processed: %d, Skipped: %d, Errors: %d. Output at: %s",
        ok_count, skipped_count, error_count, out_dir.resolve()
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

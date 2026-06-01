#!/usr/bin/env python3
"""
HTML to PDF Converter for Installation Guide

USAGE:
    python3 convert_to_pdf.py

REQUIREMENTS:
    pip install weasyprint

OUTPUT:
    Installation_Guide.pdf (in current directory)
"""

import sys
from pathlib import Path


def check_dependencies():
    """Check if weasyprint is installed."""
    try:
        import weasyprint
        return True
    except ImportError:
        return False


def convert_html_to_pdf(html_file: str, pdf_file: str) -> bool:
    """
    Convert HTML file to PDF.

    Args:
        html_file: Path to input HTML file
        pdf_file: Path to output PDF file

    Returns:
        True if successful, False otherwise
    """
    try:
        from weasyprint import HTML

        print(f"📄 Converting {html_file} to PDF...")
        HTML(html_file).write_pdf(pdf_file)

        # Check file size
        pdf_path = Path(pdf_file)
        if pdf_path.exists():
            size_kb = pdf_path.stat().st_size / 1024
            print(f"✅ PDF created successfully: {pdf_file}")
            print(f"📦 File size: {size_kb:.1f} KB")
            return True
        else:
            print(f"❌ Failed to create PDF")
            return False

    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return False


def main():
    """Main conversion workflow."""
    # Configuration
    html_file = "INSTALLATION_GUIDE.html"
    pdf_file = "Installation_Guide.pdf"

    print("=" * 60)
    print("  HTML to PDF Converter - Installation Guide")
    print("=" * 60)
    print()

    # Check if HTML file exists
    if not Path(html_file).exists():
        print(f"❌ Error: {html_file} not found")
        print(f"   Please run this script from the scripts/ directory")
        return 1

    # Check dependencies
    if not check_dependencies():
        print("❌ Error: weasyprint not installed")
        print()
        print("Please install it with:")
        print("  pip install weasyprint")
        print()
        print("Alternative methods:")
        print("  1. Open INSTALLATION_GUIDE.html in your browser")
        print("  2. Press Ctrl+P (or Cmd+P on Mac)")
        print("  3. Select 'Save as PDF'")
        print()
        print("See PDF_CONVERSION.md for more options.")
        return 1

    # Convert
    if convert_html_to_pdf(html_file, pdf_file):
        print()
        print("🎉 Success! Your PDF is ready.")
        print()
        print("Next steps:")
        print(f"  - View: open {pdf_file}")
        print(f"  - Share: Send {pdf_file} to your team")
        print(f"  - Archive: Keep for reference")
        return 0
    else:
        print()
        print("⚠️  Conversion failed. Try alternative methods:")
        print("   See PDF_CONVERSION.md for browser-based conversion")
        return 1


if __name__ == "__main__":
    sys.exit(main())

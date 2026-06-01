# Converting Installation Guide to PDF

## Method 1: Browser Print (Easiest - Works Everywhere)

### Chrome/Edge/Brave
1. Open `INSTALLATION_GUIDE.html` in your browser
2. Press `Ctrl+P` (Windows/Linux) or `Cmd+P` (Mac)
3. Select **"Save as PDF"** as the destination
4. **Recommended Settings:**
   - Paper size: A4 or Letter
   - Margins: Default
   - Options: ✅ Background graphics
   - Scale: 100%
5. Click **Save**

### Firefox
1. Open `INSTALLATION_GUIDE.html` in Firefox
2. Press `Ctrl+P` (Windows/Linux) or `Cmd+P` (Mac)
3. Select **"Microsoft Print to PDF"** or **"Save as PDF"**
4. Enable **"Print backgrounds"** in More settings
5. Click **Save**

### Safari (Mac)
1. Open `INSTALLATION_GUIDE.html` in Safari
2. Press `Cmd+P`
3. Click **PDF** dropdown in bottom-left
4. Select **"Save as PDF"**
5. Choose location and click **Save**

---

## Method 2: Command Line (Linux/Mac)

### Using wkhtmltopdf
```bash
# Install wkhtmltopdf
# Ubuntu/Debian:
sudo apt-get install wkhtmltopdf

# macOS:
brew install wkhtmltopdf

# Convert to PDF
wkhtmltopdf INSTALLATION_GUIDE.html Installation_Guide.pdf
```

### Using Pandoc + WeasyPrint
```bash
# Install dependencies
pip install weasyprint

# Convert to PDF
weasyprint INSTALLATION_GUIDE.html Installation_Guide.pdf
```

### Using headless Chrome
```bash
# Linux
google-chrome --headless --print-to-pdf=Installation_Guide.pdf INSTALLATION_GUIDE.html

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless --print-to-pdf=Installation_Guide.pdf \
  file:///$(pwd)/INSTALLATION_GUIDE.html
```

---

## Method 3: Online Converters (No Installation)

**Recommended Services:**
1. **CloudConvert** - https://cloudconvert.com/html-to-pdf
   - Upload `INSTALLATION_GUIDE.html`
   - Click "Convert"
   - Download PDF

2. **PDF24** - https://tools.pdf24.org/en/html-to-pdf
   - Drag and drop HTML file
   - Convert and download

3. **Sejda** - https://www.sejda.com/html-to-pdf
   - Upload HTML
   - Convert to PDF

⚠️ **Privacy Note:** For sensitive documents, use local conversion methods.

---

## Method 4: Python Script (Automated)

```python
#!/usr/bin/env python3
"""
Simple HTML to PDF converter using weasyprint
"""
from weasyprint import HTML

# Convert
HTML('INSTALLATION_GUIDE.html').write_pdf('Installation_Guide.pdf')
print("✅ PDF created: Installation_Guide.pdf")
```

**Install dependencies:**
```bash
pip install weasyprint
```

**Run:**
```bash
python3 convert_to_pdf.py
```

---

## Recommended Settings for Professional PDFs

**Optimal Print Settings:**
- **Paper Size:** A4 (210 × 297 mm) or US Letter (8.5 × 11 in)
- **Orientation:** Portrait
- **Margins:** Normal (2cm / 0.8in)
- **Color:** Color (not Black & White)
- **Quality:** High / Best
- **Background Graphics:** ✅ Enabled (preserves styling)
- **Headers/Footers:** ❌ Disabled (document has own)

**File Size Optimization:**
After conversion, compress if needed:
```bash
# Using Ghostscript (high quality, smaller size)
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 \
   -dPDFSETTINGS=/printer -dNOPAUSE -dQUIET -dBATCH \
   -sOutputFile=Installation_Guide_compressed.pdf \
   Installation_Guide.pdf
```

---

## Verification Checklist

After converting to PDF, verify:
- ☐ All sections are visible and readable
- ☐ Code blocks are properly formatted
- ☐ Tables are aligned correctly
- ☐ Colors and styling are preserved
- ☐ Links are clickable (if supported)
- ☐ No content is cut off at page margins
- ☐ Table of contents is complete
- ☐ File size is reasonable (< 5 MB)

---

## Troubleshooting

### "Background graphics missing"
**Solution:** Enable "Background graphics" or "Print backgrounds" in print settings.

### "Text is cut off"
**Solution:** Adjust margins to "Default" or reduce scale to 90%.

### "Colors look washed out"
**Solution:** Ensure "Color" mode is selected, not "Black & White".

### "File size is too large"
**Solution:** Use Ghostscript compression (see above) or adjust print quality.

---

## Quick Reference Commands

```bash
# Browser method (easiest)
# Open HTML → Ctrl+P → Save as PDF

# wkhtmltopdf (simple, fast)
wkhtmltopdf INSTALLATION_GUIDE.html Installation_Guide.pdf

# WeasyPrint (Python, best quality)
pip install weasyprint
python3 -c "from weasyprint import HTML; HTML('INSTALLATION_GUIDE.html').write_pdf('Installation_Guide.pdf')"

# Chrome headless (good quality)
google-chrome --headless --print-to-pdf=Installation_Guide.pdf INSTALLATION_GUIDE.html
```

---

**Recommended Method:** Use **Chrome/Edge Print to PDF** for best results with minimal setup.

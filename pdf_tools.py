import os
import io
import re
import math
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

try:
    from pdf2docx import Converter
    HAS_PDF2DOCX = True
except ImportError:
    HAS_PDF2DOCX = False

try:
    import docx
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    HAS_DOCX_REPORTLAB = True
except ImportError:
    HAS_DOCX_REPORTLAB = False


def format_size(num_bytes: int) -> str:
    """Format bytes into readable size string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"


def get_pdf_metadata(pdf_path: str) -> Dict[str, Any]:
    """Retrieve metadata, page count, and dimensions of a PDF."""
    info = {
        "page_count": 0,
        "file_size": format_size(os.path.getsize(pdf_path)),
        "file_size_bytes": os.path.getsize(pdf_path),
        "title": "Untitled",
        "author": "Unknown",
        "is_encrypted": False,
        "pages_info": []
    }
    
    try:
        doc = fitz.open(pdf_path)
        info["is_encrypted"] = doc.is_encrypted
        info["page_count"] = len(doc)
        meta = doc.metadata or {}
        if meta.get("title"):
            info["title"] = meta["title"]
        if meta.get("author"):
            info["author"] = meta["author"]
        
        for i in range(min(5, len(doc))):
            page = doc[i]
            rect = page.rect
            info["pages_info"].append({
                "page": i + 1,
                "width": round(rect.width),
                "height": round(rect.height)
            })
        doc.close()
    except Exception as e:
        info["error"] = str(e)
        
    return info


def compress_pdf(input_path: str, output_path: str) -> Dict[str, Any]:
    """
    Compress a PDF using PyMuPDF deflation, stream cleaning, and image recompression.
    """
    doc = fitz.open(input_path)
    orig_size = os.path.getsize(input_path)
    
    # Compress embedded images if possible
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                if base_img and "image" in base_img:
                    raw_bytes = base_img["image"]
                    pil_img = Image.open(io.BytesIO(raw_bytes))
                    if pil_img.mode in ("RGBA", "P"):
                        pil_img = pil_img.convert("RGB")
                    out_io = io.BytesIO()
                    pil_img.save(out_io, format="JPEG", quality=68, optimize=True)
                    new_bytes = out_io.getvalue()
                    if len(new_bytes) < len(raw_bytes):
                        doc.update_stream(xref, new_bytes)
            except Exception:
                continue

    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True
    )
    doc.close()
    
    new_size = os.path.getsize(output_path)
    reduction = max(0.0, (1.0 - (new_size / orig_size)) * 100.0) if orig_size > 0 else 0.0
    
    return {
        "success": True,
        "original_size": format_size(orig_size),
        "compressed_size": format_size(new_size),
        "reduction_pct": f"{reduction:.1f}%",
        "output_path": output_path
    }


def merge_pdfs(pdf_paths: List[str], output_path: str) -> Dict[str, Any]:
    """Merge multiple PDF files into one in order."""
    if not pdf_paths:
        raise ValueError("No PDF paths provided for merge")
        
    valid_paths = [p for p in pdf_paths if p and os.path.exists(p) and os.path.getsize(p) > 0]
    if not valid_paths:
        raise ValueError("None of the queued PDF files were found on disk or they were empty.")
        
    merged_doc = fitz.open()
    total_pages = 0
    merged_count = 0
    
    for p in valid_paths:
        try:
            doc = fitz.open(p)
            if not doc.is_pdf:
                doc.close()
                continue
            merged_doc.insert_pdf(doc)
            total_pages += len(doc)
            merged_count += 1
            doc.close()
        except Exception as e:
            logger.warning(f"Skipping unreadable or invalid PDF during merge {p}: {e}")
            
    if merged_count == 0 or total_pages == 0:
        raise ValueError("Could not extract any valid PDF pages from the uploaded documents.")
        
    merged_doc.save(output_path, garbage=3, deflate=True)
    merged_doc.close()
    
    return {
        "success": True,
        "merged_count": merged_count,
        "total_pages": total_pages,
        "output_size": format_size(os.path.getsize(output_path)),
        "output_path": output_path
    }


def parse_page_range(range_str: str, max_pages: int) -> List[int]:
    """Parse string like '1-3, 5, 8-10' into 0-indexed list of page indices."""
    if not range_str or range_str.strip().lower() in ("all", "*"):
        return list(range(max_pages))
        
    pages = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            match = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
            if match:
                start = max(1, int(match.group(1)))
                end = min(max_pages, int(match.group(2)))
                for p in range(start, end + 1):
                    pages.add(p - 1)
        elif part.isdigit():
            val = int(part)
            if 1 <= val <= max_pages:
                pages.add(val - 1)
                
    return sorted(list(pages))


def split_pdf(input_path: str, output_path: str, page_range_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract specified pages from a PDF.
    If page_range_str is provided (e.g. '1-3'), extracts those pages into output_path.
    If page_range_str is None or 'all', creates a zip archive of all single-page PDFs.
    """
    doc = fitz.open(input_path)
    max_pages = len(doc)
    
    if not page_range_str or page_range_str.strip().lower() in ("all", "each"):
        # Split all pages into individual PDFs inside a zip archive
        zip_output = output_path if output_path.endswith(".zip") else output_path + ".zip"
        with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(max_pages):
                single_doc = fitz.open()
                single_doc.insert_pdf(doc, from_page=i, to_page=i)
                buf = io.BytesIO()
                single_doc.save(buf)
                single_doc.close()
                zf.writestr(f"page_{i + 1}.pdf", buf.getvalue())
        doc.close()
        return {
            "success": True,
            "mode": "all_pages_zip",
            "page_count": max_pages,
            "output_path": zip_output
        }
    else:
        # Extract selected pages
        target_indices = parse_page_range(page_range_str, max_pages)
        if not target_indices:
            doc.close()
            raise ValueError(f"No valid pages found in range '{page_range_str}'. Total pages: {max_pages}")
            
        new_doc = fitz.open()
        for idx in target_indices:
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
            
        new_doc.save(output_path, garbage=3, deflate=True)
        new_doc.close()
        doc.close()
        
        return {
            "success": True,
            "mode": "range",
            "extracted_pages": len(target_indices),
            "output_path": output_path
        }


def pdf_to_docx(input_path: str, output_path: str) -> Dict[str, Any]:
    """Convert PDF to editable Microsoft Word (.docx) document."""
    if not HAS_PDF2DOCX:
        raise RuntimeError("pdf2docx library is not available")
        
    cv = Converter(input_path)
    cv.convert(output_path, start=0, end=None)
    cv.close()
    
    return {
        "success": True,
        "output_path": output_path,
        "output_size": format_size(os.path.getsize(output_path))
    }


def docx_to_pdf(input_path: str, output_path: str) -> Dict[str, Any]:
    """Convert a Word document (.docx) to PDF."""
    if not HAS_DOCX_REPORTLAB:
        raise RuntimeError("python-docx or reportlab is not available")
        
    doc = docx.Document(input_path)
    styles = getSampleStyleSheet()
    normal_style = styles["Normal"]
    normal_style.fontSize = 10.5
    normal_style.leading = 14
    
    title_style = ParagraphStyle(
        'DocxTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        spaceAfter=12
    )
    
    story = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            story.append(Spacer(1, 8))
            continue
            
        # Clean basic XML chars for reportlab
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if p.style.name.startswith("Heading"):
            story.append(Paragraph(safe_text, title_style))
        else:
            story.append(Paragraph(safe_text, normal_style))
        story.append(Spacer(1, 4))
        
    pdf_doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    pdf_doc.build(story)
    
    return {
        "success": True,
        "output_path": output_path,
        "output_size": format_size(os.path.getsize(output_path))
    }


def pdf_to_images(input_path: str, output_zip_path: str, dpi: int = 150) -> Tuple[str, Optional[str]]:
    """
    Render all pages of a PDF into high-res JPG images packaged in a zip archive.
    Also exports the first page preview image and returns (zip_path, preview_image_path).
    """
    doc = fitz.open(input_path)
    first_page_preview = None
    preview_path = output_zip_path.replace(".zip", "_page_1.jpg")
    
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("jpeg")
            zf.writestr(f"page_{i + 1:03d}.jpg", img_bytes)
            if i == 0:
                with open(preview_path, "wb") as pf:
                    pf.write(img_bytes)
                first_page_preview = preview_path
                
    doc.close()
    return output_zip_path, first_page_preview


def images_to_pdf(image_paths: List[str], output_path: str) -> Dict[str, Any]:
    """Compile a list of image files (JPG, PNG, WEBP) into a single PDF document."""
    if not image_paths:
        raise ValueError("No images provided")
        
    opened_images = []
    for p in image_paths:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        opened_images.append(im)
        
    first_image = opened_images[0]
    rest_images = opened_images[1:] if len(opened_images) > 1 else []
    
    first_image.save(
        output_path,
        "PDF",
        resolution=100.0,
        save_all=True,
        append_images=rest_images
    )
    
    return {
        "success": True,
        "images_count": len(image_paths),
        "output_path": output_path,
        "output_size": format_size(os.path.getsize(output_path))
    }


def rotate_pdf(input_path: str, output_path: str, degrees: int = 90) -> Dict[str, Any]:
    """Rotate all pages in a PDF by degrees (e.g. 90, 180, 270)."""
    doc = fitz.open(input_path)
    for page in doc:
        page.set_rotation((page.rotation + degrees) % 360)
    doc.save(output_path, garbage=3, deflate=True)
    doc.close()
    return {
        "success": True,
        "degrees": degrees,
        "output_path": output_path
    }


def protect_pdf(input_path: str, output_path: str, password: str) -> Dict[str, Any]:
    """Encrypt a PDF with AES-256 password protection."""
    doc = fitz.open(input_path)
    perm = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY
    doc.save(
        output_path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw=password,
        permissions=perm
    )
    doc.close()
    return {
        "success": True,
        "output_path": output_path
    }


def unlock_pdf(input_path: str, output_path: str, password: str) -> Dict[str, Any]:
    """Remove encryption from a password-protected PDF."""
    doc = fitz.open(input_path)
    if doc.is_encrypted:
        success = doc.authenticate(password)
        if not success:
            doc.close()
            raise ValueError("Incorrect password. Unable to unlock PDF.")
            
    doc.save(output_path, encryption=fitz.PDF_ENCRYPT_NONE)
    doc.close()
    return {
        "success": True,
        "output_path": output_path
    }


def watermark_pdf(input_path: str, output_path: str, watermark_text: str = "CONFIDENTIAL") -> Dict[str, Any]:
    """Stamp diagonal semi-transparent watermark text onto all pages."""
    doc = fitz.open(input_path)
    clean_text = watermark_text.strip().upper() or "CONFIDENTIAL"
    
    for page in doc:
        rect = page.rect
        center_x = rect.width / 2
        center_y = rect.height / 2
        
        # Calculate dynamic font size based on page width
        font_size = min(rect.width, rect.height) * 0.12
        
        # Insert diagonal text using morph matrix
        pt = fitz.Point(center_x - (len(clean_text) * font_size * 0.2), center_y)
        page.insert_text(
            pt,
            clean_text,
            fontsize=font_size,
            morph=(pt, fitz.Matrix(45)),
            color=(0.85, 0.35, 0.15),  # OpenAIPDF orange tint
            fill_opacity=0.28
        )
        
    doc.save(output_path, garbage=3, deflate=True)
    doc.close()
    return {
        "success": True,
        "watermark": clean_text,
        "output_path": output_path
    }


def summarize_pdf(input_path: str) -> Dict[str, Any]:
    """Extract text from a PDF, compute metrics, and generate an executive summary."""
    doc = fitz.open(input_path)
    total_pages = len(doc)
    full_text = []
    
    for page in doc:
        txt = page.get_text("text")
        if txt.strip():
            full_text.append(txt.strip())
            
    doc.close()
    joined_text = "\n\n".join(full_text)
    
    words = joined_text.split()
    word_count = len(words)
    char_count = len(joined_text)
    reading_time_min = max(1, round(word_count / 200))
    
    # Simple, high-quality extractive summary: select most salient sentences
    sentences = re.split(r'(?<=[.!?])\s+', joined_text)
    clean_sentences = [s.strip() for s in sentences if len(s.strip()) > 30 and len(s.strip()) < 300]
    
    # Pick top representative sentences from intro, middle, and conclusion
    if len(clean_sentences) <= 4:
        summary_sentences = clean_sentences
    else:
        indices = [0, len(clean_sentences) // 3, (2 * len(clean_sentences)) // 3, len(clean_sentences) - 1]
        summary_sentences = [clean_sentences[i] for i in sorted(list(set(indices)))]
        
    summary_text = " ".join(summary_sentences) if summary_sentences else "No extractable text found in document."
    
    return {
        "success": True,
        "pages": total_pages,
        "word_count": word_count,
        "char_count": char_count,
        "est_reading_time_min": reading_time_min,
        "summary": summary_text[:1200]
    }

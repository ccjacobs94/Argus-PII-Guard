with open("backend/scanner.py", "r") as f:
    content = f.read()

import re

old_func_pattern = re.compile(r'def get_file_text_content\(file_path: Path\) -> str:.*?(?=IMAGE_PROMPT = )', re.DOTALL)

new_func = "def _get_pdf_text(path):\n    import pypdf\n    reader = pypdf.PdfReader(path)\n    parts = []\n    for page in reader.pages[:15]:\n        extracted = page.extract_text()\n        if extracted:\n            parts.append(extracted)\n    return '\\n'.join(parts)[:4096]\n\ndef _get_docx_text(path):\n    import docx\n    doc = docx.Document(path)\n    parts = [p.text for p in doc.paragraphs if p.text.strip()]\n    for table in doc.tables:\n        for row in table.rows:\n            parts.append(' | '.join(cell.text.strip() for cell in row.cells if cell.text.strip()))\n    return '\\n'.join(parts)[:4096]\n\ndef _get_xlsx_text(path):\n    import openpyxl\n    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)\n    parts = []\n    try:\n        for sheet in wb.worksheets[:5]:\n            for row in sheet.iter_rows(values_only=True, max_row=100):\n                row_vals = [str(val).strip() for val in row if val is not None and str(val).strip()]\n                if row_vals:\n                    parts.append(' | '.join(row_vals))\n    finally:\n        wb.close()\n    return '\\n'.join(parts)[:4096]\n\ndef _get_pptx_text(path):\n    import pptx\n    prs = pptx.Presentation(path)\n    parts = []\n    for slide in prs.slides:\n        for shape in slide.shapes:\n            if shape.has_text_frame and shape.text.strip():\n                parts.append(shape.text.strip())\n    return '\\n'.join(parts)[:4096]\n\ndef get_file_text_content(file_path: Path) -> str:\n    path = Path(file_path)\n    ext = path.suffix.lower()\n    try:\n        if ext in PDF_EXTENSIONS:\n            return _get_pdf_text(path)\n        elif ext == '.docx':\n            return _get_docx_text(path)\n        elif ext in ('.xlsx', '.xls'):\n            return _get_xlsx_text(path)\n        elif ext == '.pptx':\n            return _get_pptx_text(path)\n        else:\n            return path.read_text(errors='ignore')[:4096]\n    except Exception as e:\n        print(f'Error extracting text from {path}: {e}')\n        return ''\n\n"

# By using replace on the matched string directly we completely avoid re.sub() backslash expansion issues
match = old_func_pattern.search(content)
if match:
    old_func_str = match.group(0)
    content = content.replace(old_func_str, new_func)

helper = """
def _check_cache_status(file_cache, str_path, current_checksum, mtime, size):
    cached_entry = file_cache.get(str_path)
    if not cached_entry:
        return False, None
    cached_checksum = cached_entry.get("checksum")
    is_unmodified = False
    if cached_checksum:
        if current_checksum and cached_checksum == current_checksum:
            is_unmodified = True
    else:
        if cached_entry.get("mtime") == mtime:
            is_unmodified = True
            cached_entry["checksum"] = current_checksum
            cached_entry["size"] = size
    return is_unmodified, cached_entry
"""
content = content.replace("def run_scan(folders, save_results_callback, rescan_all=False, scan_id=None):", helper + "\ndef run_scan(folders, save_results_callback, rescan_all=False, scan_id=None):")

old_cache_exact = """
        if not rescan_all and str_path in file_cache:
            cached_entry = file_cache[str_path]
            cached_checksum = cached_entry.get("checksum")

            # Determine if the file is unmodified
            is_unmodified = False
            if cached_checksum:
                if current_checksum and cached_checksum == current_checksum:
                    is_unmodified = True
            else:
                # Legacy cache migration fallback
                if cached_entry.get("mtime") == mtime:
                    is_unmodified = True
                    cached_entry["checksum"] = current_checksum
                    cached_entry["size"] = size

            if is_unmodified:
                cached_result = cached_entry.get("result")
                if not cached_result or not cached_result.get("compromised"):
                    with state_lock:
                        scan_state.progress["skipped_count"] += 1
                        scan_state.progress["scanned_files"] += 1
                    return
                else:
                    # Add previously flagged back
                    ext = file_path.suffix.lower()
                    with state_lock:
                        file_type_label = "Image" if ext in IMAGE_EXTENSIONS else "HEIC" if ext in HEIC_EXTENSIONS else "PDF" if ext in PDF_EXTENSIONS else "Office" if ext in OFFICE_EXTENSIONS else "Text"
                        scan_state.flagged_files.append({
                            "file": str_path,
                            "type": file_type_label,
                            "reason": cached_result.get("reason"),
                            "selected": False,
                            "auto_deleted": False, # Cached won't auto-delete retroactively
                            "needs_ai_verification": cached_result.get("needs_ai_verification", False),
                            "compromised": True,
                            "items": cached_result.get("items", []),
                            "snippets": cached_result.get("snippets", []),
                            "checksum": current_checksum
                        })
                        scan_state.progress["flagged_count"] = len(scan_state.flagged_files)
                        scan_state.progress["scanned_files"] += 1
                    return

        ext = file_path.suffix.lower()
"""

new_cache_exact = """
        if not rescan_all and str_path in file_cache:
            is_unmodified, cached_entry = _check_cache_status(file_cache, str_path, current_checksum, mtime, size)
            if is_unmodified:
                cached_result = cached_entry.get("result")
                if not cached_result or not cached_result.get("compromised"):
                    with state_lock:
                        scan_state.progress["skipped_count"] += 1
                        scan_state.progress["scanned_files"] += 1
                    return
                else:
                    ext = file_path.suffix.lower()
                    with state_lock:
                        file_type_label = "Image" if ext in IMAGE_EXTENSIONS else "HEIC" if ext in HEIC_EXTENSIONS else "PDF" if ext in PDF_EXTENSIONS else "Office" if ext in OFFICE_EXTENSIONS else "Text"
                        scan_state.flagged_files.append({
                            "file": str_path,
                            "type": file_type_label,
                            "reason": cached_result.get("reason"),
                            "selected": False,
                            "auto_deleted": False,
                            "needs_ai_verification": cached_result.get("needs_ai_verification", False),
                            "compromised": True,
                            "items": cached_result.get("items", []),
                            "snippets": cached_result.get("snippets", []),
                            "checksum": current_checksum
                        })
                        scan_state.progress["flagged_count"] = len(scan_state.flagged_files)
                        scan_state.progress["scanned_files"] += 1
                    return

        ext = file_path.suffix.lower()
"""

content = content.replace(old_cache_exact, new_cache_exact)

with open("backend/scanner.py", "w") as f:
    f.write(content)

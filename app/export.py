"""Structured Output: write results to CSV / Excel / JSON in ./exports."""
import csv
import io
import json
from typing import List

from openpyxl import Workbook

from .models import Company

COLUMNS = ["name", "website", "phone", "email", "address", "category", "rating", "maps_url"]
HEADERS = [
    "Company Name", "Website URL", "Phone Number", "Email Address",
    "Address", "Category", "Rating", "Google Maps URL",
]


def to_csv_bytes(companies: List[Company]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    for c in companies:
        d = c.model_dump()
        writer.writerow([d.get(col) or "" for col in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows UTF-8 correctly


def to_json_bytes(companies: List[Company]) -> bytes:
    data = [c.model_dump() for c in companies]
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def to_xlsx_bytes(companies: List[Company]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Companies"
    ws.append(HEADERS)
    for c in companies:
        d = c.model_dump()
        ws.append([d.get(col) or "" for col in COLUMNS])
    # Auto-ish column widths.
    for i, header in enumerate(HEADERS, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(18, len(header) + 4)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

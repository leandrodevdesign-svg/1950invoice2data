"""Support utilities for the invoice2data web application."""

from __future__ import annotations

import csv
import datetime
import io
import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List

from openpyxl import Workbook


RESULTS_DIR = Path("/tmp/invoice2data-web-results")


def ensure_results_dir() -> Path:
    """Create the results directory when missing and return it."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def serialize_value(value: Any, date_format: str = "%Y-%m-%d") -> str:
    """Convert extracted values into strings suitable for tables and exports."""
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime(date_format)
    if isinstance(value, (dict, list)):
        return json.dumps(_normalize_nested(value, date_format), ensure_ascii=False)
    return str(value)


def _normalize_nested(value: Any, date_format: str) -> Any:
    """Recursively normalize nested values for JSON serialization."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime(date_format)
    if isinstance(value, list):
        return [_normalize_nested(item, date_format) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize_nested(item, date_format) for key, item in value.items()
        }
    return value


def build_export_rows(results: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Flatten extraction results into a row-oriented structure."""
    rows: List[Dict[str, str]] = []
    for result in results:
        row: Dict[str, str] = {
            "source_file": serialize_value(result.get("source_file")),
            "status": serialize_value(result.get("status", "ok")),
            "message": serialize_value(result.get("message", "")),
        }
        data = result.get("data", {})
        if isinstance(data, dict):
            for key, value in data.items():
                row[str(key)] = serialize_value(value)
        rows.append(row)
    return rows


def get_table_columns(rows: Iterable[Dict[str, str]]) -> List[str]:
    """Return a stable ordered list of table columns."""
    priority = ["source_file", "status", "message"]
    discovered: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in priority and key not in discovered:
                discovered.append(key)
    return priority + sorted(discovered)


def write_csv_bytes(rows: List[Dict[str, str]], columns: List[str]) -> bytes:
    """Generate a CSV file as UTF-8 encoded bytes."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue().encode("utf-8")


def write_xlsx_bytes(rows: List[Dict[str, str]], columns: List[str]) -> bytes:
    """Generate an XLSX workbook as bytes."""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Invoices"
    worksheet.append(columns)
    for row in rows:
        worksheet.append([row.get(column, "") for column in columns])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()

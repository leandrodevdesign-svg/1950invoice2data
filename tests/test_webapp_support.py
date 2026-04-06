"""Tests for the web application support utilities."""

import datetime
import io
import zipfile

from invoice2data.webapp_support import build_export_rows
from invoice2data.webapp_support import get_table_columns
from invoice2data.webapp_support import serialize_value
from invoice2data.webapp_support import write_csv_bytes
from invoice2data.webapp_support import write_xlsx_bytes


def test_build_export_rows_flattens_invoice_data() -> None:
    rows = build_export_rows(
        [
            {
                "source_file": "invoice-01.pdf",
                "status": "ok",
                "message": "",
                "data": {
                    "issuer": "ACME",
                    "date": datetime.datetime(2024, 1, 15),
                    "amount": 123.45,
                    "hours": 8,
                },
            }
        ]
    )

    assert rows == [
        {
            "source_file": "invoice-01.pdf",
            "status": "ok",
            "message": "",
            "issuer": "ACME",
            "date": "2024-01-15",
            "amount": "123.45",
            "hours": "8",
        }
    ]


def test_get_table_columns_keeps_priority_columns_first() -> None:
    columns = get_table_columns(
        [
            {"status": "ok", "issuer": "ACME", "source_file": "a.pdf"},
            {"status": "error", "message": "failed", "amount": "10.00"},
        ]
    )
    assert columns[:3] == ["source_file", "status", "message"]
    assert "issuer" in columns
    assert "amount" in columns


def test_csv_and_xlsx_writers_generate_content() -> None:
    rows = [{"source_file": "a.pdf", "status": "ok", "message": "", "amount": "10"}]
    columns = ["source_file", "status", "message", "amount"]

    csv_bytes = write_csv_bytes(rows, columns)
    xlsx_bytes = write_xlsx_bytes(rows, columns)

    assert b"source_file,status,message,amount" in csv_bytes
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        assert "xl/workbook.xml" in archive.namelist()


def test_serialize_value_normalizes_nested_values() -> None:
    value = {
        "lines": [{"worked_at": datetime.date(2024, 2, 1), "hours": 5}],
        "issuer": "ACME",
    }
    serialized = serialize_value(value)
    assert '"worked_at": "2024-02-01"' in serialized

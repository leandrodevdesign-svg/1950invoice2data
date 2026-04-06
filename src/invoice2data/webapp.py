"""Simple web UI for uploading invoices and exporting extracted data."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

from invoice2data import extract_data
from invoice2data.extract.loader import read_templates

from .webapp_support import build_export_rows
from .webapp_support import ensure_results_dir
from .webapp_support import get_table_columns
from .webapp_support import write_csv_bytes
from .webapp_support import write_xlsx_bytes


APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "web_templates"))
app = FastAPI(title="invoice2data reviewer")


def load_web_templates() -> List[Any]:
    """Load templates for the web app."""
    custom_template_folder = os.getenv("INVOICE2DATA_TEMPLATE_FOLDER")
    templates_loaded: List[Any] = []
    if custom_template_folder:
        templates_loaded.extend(read_templates(custom_template_folder))
    if os.getenv("INVOICE2DATA_EXCLUDE_BUILTIN", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        templates_loaded.extend(read_templates())
    return templates_loaded


def get_input_reader_name() -> str:
    """Return the input reader used by the web app."""
    return os.getenv("INVOICE2DATA_INPUT_READER", "pdfminer")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the upload form."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "results": [],
            "columns": [],
            "download_id": None,
            "input_reader": get_input_reader_name(),
        },
    )


@app.post("/extract", response_class=HTMLResponse)
async def extract_view(
    request: Request,
    files: List[UploadFile] = File(...),
) -> HTMLResponse:
    """Process uploaded invoice files and render a results table."""
    if not files:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "results": [],
                "columns": [],
                "download_id": None,
                "error": "Sube al menos un PDF para procesar.",
                "input_reader": get_input_reader_name(),
            },
            status_code=400,
        )

    extraction_templates = load_web_templates()
    extraction_results = await process_uploads(files, extraction_templates)
    export_rows = build_export_rows(extraction_results)
    columns = get_table_columns(export_rows)
    download_id = persist_exports(export_rows, columns)
    summary = summarize_results(extraction_results)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "results": export_rows,
            "columns": columns,
            "download_id": download_id,
            "summary": summary,
            "input_reader": get_input_reader_name(),
        },
    )


@app.get("/downloads/{download_id}/{filetype}")
async def download_file(download_id: str, filetype: str) -> FileResponse:
    """Download generated export files."""
    allowed = {"csv", "xlsx", "json"}
    if filetype not in allowed:
        raise HTTPException(status_code=404, detail="Tipo de archivo no soportado.")

    output_path = ensure_results_dir() / f"{download_id}.{filetype}"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    media_types = {
        "csv": "text/csv; charset=utf-8",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
    }
    return FileResponse(
        path=output_path,
        media_type=media_types[filetype],
        filename=f"invoice-review.{filetype}",
    )


async def process_uploads(
    files: List[UploadFile],
    extraction_templates: List[Any],
) -> List[Dict[str, Any]]:
    """Run the extractor against a list of uploaded PDFs."""
    results: List[Dict[str, Any]] = []
    input_reader = get_input_reader_name()

    for upload in files:
        suffix = Path(upload.filename or "invoice.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(await upload.read())

        try:
            extracted = extract_data(
                str(temp_path),
                templates=extraction_templates,
                input_module=input_reader,
            )
            if extracted:
                results.append(
                    {
                        "source_file": upload.filename,
                        "status": "ok",
                        "message": "",
                        "data": extracted,
                    }
                )
            else:
                results.append(
                    {
                        "source_file": upload.filename,
                        "status": "sin_coincidencia",
                        "message": "No se encontró una plantilla válida para este archivo.",
                        "data": {},
                    }
                )
        except Exception as error:
            results.append(
                {
                    "source_file": upload.filename,
                    "status": "error",
                    "message": str(error),
                    "data": {},
                }
            )
        finally:
            temp_path.unlink(missing_ok=True)

    return results


def persist_exports(rows: List[Dict[str, str]], columns: List[str]) -> str:
    """Persist export artifacts in a temporary folder and return their id."""
    results_dir = ensure_results_dir()
    download_id = uuid.uuid4().hex

    csv_path = results_dir / f"{download_id}.csv"
    xlsx_path = results_dir / f"{download_id}.xlsx"
    json_path = results_dir / f"{download_id}.json"

    csv_path.write_bytes(write_csv_bytes(rows, columns))
    xlsx_path.write_bytes(write_xlsx_bytes(rows, columns))
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return download_id


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, int]:
    """Build a small processing summary for the UI."""
    summary = {"total": len(results), "ok": 0, "sin_coincidencia": 0, "error": 0}
    for result in results:
        status = result.get("status")
        if status in summary:
            summary[status] += 1
    return summary


def main() -> None:
    """Run the development web server."""
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("invoice2data.webapp:app", host="0.0.0.0", port=port)

"""FastAPI application wiring the whole pipeline together.

Pipeline (mirrors the architecture diagram):
  User Query -> AI Agent (Groq) -> Maps Scraper (Playwright)
             -> Website Enrichment -> Validation -> Structured Output
"""
import asyncio
import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import SearchRequest, SearchResponse, Company
from . import ai_agent, scraper, enrichment, validation, export

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Maps Company Scraper", version="1.0.0")


# ----------------------------- core pipeline -----------------------------
async def run_pipeline(query: str, max_results: int, enrich: bool, log=lambda m: None) -> SearchResponse:
    log("Understanding your query...")
    parsed = ai_agent.understand_query(query)
    log(f"Category: '{parsed.category}'  |  Location: '{parsed.location}'")

    companies = await scraper.scrape_maps(parsed.search_term, max_results, log)

    if enrich and companies:
        log("Enriching websites to find email addresses...")
        companies = await enrichment.enrich_companies(companies)

    log("Validating and de-duplicating results...")
    companies = validation.validate_companies(companies)

    log(f"Done — {len(companies)} companies.")
    return SearchResponse(query=query, parsed=parsed, count=len(companies), results=companies)


# ----------------------------- JSON endpoint -----------------------------
@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    max_results = req.max_results or settings.max_results
    enrich = settings.enrich_websites if req.enrich is None else req.enrich
    return await run_pipeline(req.query, max_results, enrich)


# ----------------------------- SSE streaming -----------------------------
@app.get("/api/stream")
async def stream(query: str, max_results: int | None = None, enrich: bool | None = None):
    mr = max_results or settings.max_results
    en = settings.enrich_websites if enrich is None else enrich
    queue: asyncio.Queue = asyncio.Queue()

    def log(msg: str):
        queue.put_nowait(("log", msg))

    async def worker():
        try:
            result = await run_pipeline(query, mr, en, log)
            queue.put_nowait(("result", result.model_dump()))
        except Exception as exc:  # noqa: BLE001
            queue.put_nowait(("error", str(exc)))
        finally:
            queue.put_nowait(("done", None))

    async def event_gen():
        task = asyncio.create_task(worker())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "done":
                    yield _sse("done", {})
                    break
                yield _sse(kind, payload if kind != "log" else {"message": payload})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ----------------------------- exports -----------------------------------
@app.post("/api/export/{fmt}")
async def export_results(fmt: str, companies: List[Company]):
    fmt = fmt.lower()
    if fmt == "csv":
        return Response(export.to_csv_bytes(companies), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=companies.csv"})
    if fmt == "json":
        return Response(export.to_json_bytes(companies), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=companies.json"})
    if fmt in ("xlsx", "excel"):
        return Response(
            export.to_xlsx_bytes(companies),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=companies.xlsx"},
        )
    return JSONResponse({"error": f"unknown format '{fmt}'"}, status_code=400)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ----------------------------- frontend ----------------------------------
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

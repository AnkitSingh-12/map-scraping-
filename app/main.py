"""FastAPI application wiring the whole pipeline together.

Pipeline (mirrors the architecture diagram):
  User Query -> AI Agent (Groq) -> Maps Scraper (Playwright)
             -> Website Enrichment -> Validation -> Structured Output
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List

# Setup sys.path to resolve relative import issues when executing directly
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from app.config import settings
from app.models import SearchRequest, SearchResponse, Company
from app import ai_agent, scraper, enrichment, validation, export, categorizer, database

FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    await database.init_db()
    yield


app = FastAPI(title="Maps Company Scraper", version="1.0.0", lifespan=lifespan)


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

    log("Categorizing companies using Automaton Layer...")
    for company in companies:
        company.category = categorizer.company_categorizer.categorize(company)

    await database.save_companies(query, companies, log)

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


@app.get("/api/db-companies")
async def get_db_companies():
    try:
        import asyncpg
        params = await database.get_connection_params()
        conn = await asyncpg.connect(**params)
        try:
            rows = await conn.fetch("SELECT id, query, name, maps_url, website, phone, email, address, category, rating, created_at FROM companies ORDER BY id DESC")
            # Convert record objects to dictionary with serializable values
            results = []
            for r in rows:
                d = dict(r)
                if d.get("created_at"):
                    d["created_at"] = d["created_at"].isoformat()
                results.append(d)
            return results
        finally:
            await conn.close()
    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch database records: {e}"}, status_code=500)


# ----------------------------- frontend ----------------------------------
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8012, reload=True)


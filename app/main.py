"""FastAPI dashboard/API for AI Application Engineer portfolio project."""
from __future__ import annotations
import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from io import BytesIO
from decimal import Decimal
from typing import Annotated
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db, ImportBatch, LedgerRow
from app.etl import import_excel, MAX_BYTES
from app.reports import dashboard, filtered_rows, summarize, workbook_bytes, ALLOWED_GROUPS
from app.agent import plan

MAX_UPLOAD_REQUEST_BYTES = MAX_BYTES + (1024 * 1024)
MAX_JSON_REQUEST_BYTES = 8 * 1024


def valid_api_key(candidate: str | None) -> bool:
    key = os.getenv("APP_API_KEY", "")
    return bool(key and candidate and hmac.compare_digest(candidate, key))


class EarlyAPIRequestGate:
    """Authenticate and bound protected request bodies before FastAPI parses them."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope.get("type") != "http" or not (path == "/api" or path.startswith("/api/")):
            await self.application(scope, receive, send)
            return

        headers: dict[bytes, bytes] = {}
        for name, value in scope.get("headers", []):
            headers.setdefault(name.lower(), value)
        supplied = headers.get(b"x-api-key", b"").decode("latin-1")
        if not valid_api_key(supplied):
            await JSONResponse({"detail":"Valid X-API-Key required"}, status_code=401)(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in {"POST", "PUT", "PATCH"}:
            await self.application(scope, receive, send)
            return
        canonical_path = path.rstrip("/") or "/"
        limit = MAX_UPLOAD_REQUEST_BYTES if canonical_path == "/api/imports" else MAX_JSON_REQUEST_BYTES
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                content_length = int(raw_length)
            except ValueError:
                await JSONResponse({"detail":"Invalid Content-Length"}, status_code=400)(scope, receive, send)
                return
            if content_length < 0:
                await JSONResponse({"detail":"Invalid Content-Length"}, status_code=400)(scope, receive, send)
                return
            if content_length > limit:
                await JSONResponse({"detail":"Request body too large"}, status_code=413)(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await JSONResponse({"detail":"Request body too large"}, status_code=413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        delivered = False
        response_finished = asyncio.Event()

        async def replay_receive():
            nonlocal delivered
            if delivered:
                await response_finished.wait()
                return {"type":"http.disconnect"}
            delivered = True
            return {"type":"http.request", "body":bytes(body), "more_body":False}
        try:
            await self.application(scope, replay_receive, send)
        finally:
            response_finished.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("APP_API_KEY"):
        raise RuntimeError("Set APP_API_KEY before running. See .env.example")
    init_db()
    yield

app=FastAPI(title="Enterprise Excel AI Copilot",version="0.1.0",lifespan=lifespan,
            description="Audited Excel ETL, safe summary queries and formatted exports. Not a production ERP integration.")
app.add_middleware(EarlyAPIRequestGate)


def guard(x_api_key: Annotated[str | None, Header()] = None) -> None:
    if not valid_api_key(x_api_key):
        raise HTTPException(status_code=401,detail="Valid X-API-Key required")

def session():
    with SessionLocal() as s:
        yield s

class AskRequest(BaseModel):
    question: str = Field(min_length=3,max_length=500)

@app.get("/",include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent/"static"/"index.html")

@app.get("/app.css",include_in_schema=False)
def css():
    return FileResponse(Path(__file__).parent/"static"/"app.css",media_type="text/css")

@app.get("/app.js",include_in_schema=False)
def js():
    return FileResponse(Path(__file__).parent/"static"/"app.js",media_type="application/javascript")

@app.get("/healthz")
def health():
    return {"status":"ok","service":"excel-copilot","version":"0.1.0"}

@app.get("/api/overview",dependencies=[Depends(guard)])
def overview(db: Session=Depends(session)):
    return dashboard(db)

@app.get("/api/batches",dependencies=[Depends(guard)])
def batches(db: Session=Depends(session)):
    allb=db.scalars(select(ImportBatch).order_by(ImportBatch.uploaded_at.desc()).limit(25)).all()
    return [{"id":b.id,"filename":b.filename,"uploaded_at":b.uploaded_at.isoformat(),"scanned":b.scanned,"accepted":b.accepted,"rejected":b.rejected,"duplicates":b.duplicates,"issues":json.loads(b.issues_json)} for b in allb]

@app.get("/api/records",dependencies=[Depends(guard)])
def records(limit:int=Query(25,ge=1,le=200),db:Session=Depends(session)):
    rows=db.scalars(select(LedgerRow).order_by(LedgerRow.txn_date.desc()).limit(limit)).all()
    batch_names = {b.id:b.filename for b in db.scalars(select(ImportBatch)).all()}
    return [{"document_no":r.document_no,"date":r.txn_date.isoformat(),"department":r.department,
        "counterparty":r.counterparty,"entry_type":r.entry_type,"amount_vnd":format(r.amount,".2f"),
        "status":r.status,"source_file":batch_names.get(r.batch_id,"unknown"),"source_sheet":r.source_sheet,
        "source_row":r.source_row,"batch_id":r.batch_id} for r in rows]

@app.post("/api/imports",dependencies=[Depends(guard)])
def create_import(file: UploadFile=File(...),db:Session=Depends(session)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=415,detail="Only .xlsx files are allowed")
    data=file.file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:
        raise HTTPException(status_code=413,detail="File too large (8MB maximum)")
    try:
        return import_excel(db,file.filename or "unknown.xlsx",data)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422,detail=str(exc)) from exc

@app.get("/api/reports/summary",dependencies=[Depends(guard)])
def report_summary(group_by:str="department",from_date:date|None=None,to_date:date|None=None,db:Session=Depends(session)):
    if group_by not in ALLOWED_GROUPS:
        raise HTTPException(status_code=422,detail="group_by not allowed")
    if from_date and to_date and from_date>to_date:
        raise HTTPException(status_code=422,detail="from_date must precede to_date")
    return summarize(filtered_rows(db,from_date,to_date),group_by)

@app.get("/api/reports/summary.xlsx",dependencies=[Depends(guard)])
def report_xlsx(group_by:str="department",db:Session=Depends(session)):
    if group_by not in ALLOWED_GROUPS:
        raise HTTPException(status_code=422,detail="group_by not allowed")
    rows=filtered_rows(db)
    groups=summarize(rows,group_by)
    issues=batch_issues(db)
    blob=workbook_bytes(rows,groups,issues)
    return StreamingResponse(BytesIO(blob),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      headers={"Content-Disposition":'attachment; filename="enterprise-summary.xlsx"',"Cache-Control":"no-store"})

@app.post("/api/ask",dependencies=[Depends(guard)])
def ask(payload:AskRequest,db:Session=Depends(session)):
    try:
        intent,source=plan(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    result=summarize(filtered_rows(db),intent.group_by)
    metric_total=result["totals"].get(intent.metric.upper()) if intent.metric!="overview" else None
    return {"question":payload.question,"planner":source,"intent":intent.model_dump(),"report":result,
      "applied_filters":{"from_date":None,"to_date":None,"department":None},
      "source":{"accepted_records":result["count"],"dataset":"normalized ledger rows"},
      "answer":(f"{intent.metric.title()} total across all accepted records: {display_money(metric_total)} VND." if metric_total is not None else f"{result['count']} accepted rows; revenue {display_money(result['totals']['REVENUE'])} VND, expense {display_money(result['totals']['EXPENSE'])} VND, net {display_money(result['net'])} VND."),
      "caveat":"Only normalized accepted records. This is not financial or accounting certification."}

@app.post("/api/ask/export",dependencies=[Depends(guard)])
def ask_export(payload:AskRequest,db:Session=Depends(session)):
    try:
        intent,_=plan(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    rows=filtered_rows(db)
    blob=workbook_bytes(rows,summarize(rows,intent.group_by),batch_issues(db))
    return StreamingResponse(BytesIO(blob),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      headers={"Content-Disposition":'attachment; filename="ai-question-report.xlsx"',"Cache-Control":"no-store"})


def batch_issues(db: Session) -> list[dict]:
    all_batches=db.scalars(select(ImportBatch).order_by(ImportBatch.uploaded_at.desc()).limit(50)).all()
    return [dict(issue,file=batch.filename) for batch in all_batches for issue in json.loads(batch.issues_json)]


def display_money(value: object) -> str:
    amount = Decimal(str(value))
    return f"{amount:,.0f}" if amount == amount.to_integral() else f"{amount:,.2f}"

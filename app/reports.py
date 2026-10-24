"""Controlled aggregations and Excel workbook generation. No raw SQL from end users."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from io import BytesIO
import json
import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from app.database import LedgerRow, ImportBatch

ALLOWED_GROUPS = {"department", "month", "entry_type", "status"}
MONEY_QUANTUM = Decimal("0.01")


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM)


def money_text(value: object) -> str:
    return format(money_decimal(value), ".2f")


def excel_money(value: object) -> float | str:
    """Use a numeric Excel cell only when float round-trips to the exact cents."""
    exact = money_decimal(value)
    candidate = float(exact)
    if money_decimal(candidate) == exact:
        return candidate
    return money_text(exact)


def filtered_rows(db: Session, from_date: date | None=None, to_date: date | None=None) -> list[LedgerRow]:
    query = select(LedgerRow).options(selectinload(LedgerRow.batch))
    if from_date: query=query.where(LedgerRow.txn_date >= from_date)
    if to_date: query=query.where(LedgerRow.txn_date <= to_date)
    return db.scalars(query.order_by(LedgerRow.txn_date,LedgerRow.id)).all()


def dataframe(rows: list[LedgerRow]) -> pd.DataFrame:
    return pd.DataFrame([{
        "document_no":r.document_no,"date":r.txn_date.isoformat(),"month":r.txn_date.strftime("%Y-%m"),
        "department":r.department,"counterparty":r.counterparty,"entry_type":r.entry_type,
        "amount_vnd":excel_money(r.amount),"status":r.status,"source_sheet":r.source_sheet,
        "source_row":r.source_row,"source_file":(r.batch.filename if r.batch else "demo"),
        "source_batch_id":r.batch_id,
    } for r in rows],columns=["document_no","date","month","department","counterparty","entry_type","amount_vnd","status","source_sheet","source_row","source_file","source_batch_id"])


def summarize(rows: list[LedgerRow], group_by: str = "department") -> dict:
    if group_by not in ALLOWED_GROUPS: raise ValueError("Unsupported group_by")
    kinds = ("REVENUE","EXPENSE","RECEIVABLE","PAYABLE")
    totals = {kind: Decimal("0.00") for kind in kinds}
    grouped: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        amount = money_decimal(row.amount)
        totals[row.entry_type] += amount
        key = row.txn_date.strftime("%Y-%m") if group_by == "month" else str(getattr(row, group_by))
        bucket = grouped.setdefault(key, {kind: Decimal("0.00") for kind in kinds})
        bucket[row.entry_type] += amount
    groups = []
    for key in sorted(grouped):
        bucket = grouped[key]
        groups.append({"group":key,"revenue":money_text(bucket["REVENUE"]),
            "expense":money_text(bucket["EXPENSE"]),"receivable":money_text(bucket["RECEIVABLE"]),
            "payable":money_text(bucket["PAYABLE"]),"net":money_text(bucket["REVENUE"]-bucket["EXPENSE"])})
    return {"count":len(rows),"group_by":group_by,"totals":{kind:money_text(value) for kind,value in totals.items()},
            "net":money_text(totals["REVENUE"]-totals["EXPENSE"]),"groups":groups,
            "note":"Net = Revenue - Expense. Receivable/Payable are reported separately, not double-counted."}


def dashboard(db: Session) -> dict:
    rows = filtered_rows(db)
    data = summarize(rows)
    n_b = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    n_r = db.scalar(select(func.sum(ImportBatch.rejected))) or 0
    n_d = db.scalar(select(func.sum(ImportBatch.duplicates))) or 0
    data.update({"batch_count":int(n_b),"rejected_rows":int(n_r),"duplicate_rows":int(n_d)})
    return data


def workbook_bytes(rows: list[LedgerRow], grouped: dict, batch_issues: list[dict] | None = None) -> bytes:
    """Exports aggregate + source rows + issues. Pivot-style table, not native PivotTable."""
    frame = dataframe(rows)
    summary = pd.DataFrame(grouped["groups"],columns=["group","revenue","expense","receivable","payable","net"])
    for column in ("revenue","expense","receivable","payable","net"):
        if column in summary:
            summary[column] = summary[column].map(excel_money)
    quality = pd.DataFrame(batch_issues or [], columns=["file","sheet","row","reason"])
    out = BytesIO()
    with pd.ExcelWriter(out,engine="xlsxwriter",datetime_format="yyyy-mm-dd",engine_kwargs={"options":{"strings_to_formulas":False,"strings_to_urls":False}}) as writer:
        book = writer.book
        title = book.add_format({"bold":True,"font_size":17,"font_color":"#0F3D52"})
        sub = book.add_format({"font_color":"#475569","font_size":10})
        money = book.add_format({"num_format":"#,##0.00;[Red](#,##0.00)","font_color":"#0F172A"})
        header = book.add_format({"bold":True,"font_color":"#FFFFFF","bg_color":"#0E7490","border":0,"align":"center"})
        warn = book.add_format({"font_color":"#9A3412","bg_color":"#FFF7ED"})
        meta = book.add_worksheet("Read Me")
        meta.write("A1","ENTERPRISE DATA COPILOT",title)
        meta.write("A3","Report type")
        meta.write("B3",f"Pivot-style grouped summary by {grouped['group_by']}")
        meta.write("A4","Definition")
        meta.write("B4",grouped["note"])
        meta.write("A5","Governance")
        meta.write("B5","Computed from accepted rows only; see Data Quality for rejects")
        meta.set_column("A:A",24)
        meta.set_column("B:B",94)
        for sheetname,data in [("Summary",summary),("Normalized Data",frame),("Data Quality",quality)]:
            data.to_excel(writer,sheet_name=sheetname,index=False,startrow=3)
            ws=writer.sheets[sheetname]
            ws.write("A1",{"Summary":"GROUPED FINANCIAL OVERVIEW","Normalized Data":"NORMALIZED TRANSACTIONS","Data Quality":"QUALITY / REJECTION LOG"}[sheetname],title)
            ws.write("A2","Synthetic demo or user-provided data. Filter rows; do not infer accounting compliance.",sub)
            ws.freeze_panes(4,0)
            ws.set_zoom(90)
            ws.set_row(3,23)
            for i,column in enumerate(data.columns):
                ws.write(3,i,column.upper().replace("_"," "),header)
                ws.set_column(i,i,22 if column not in {"reason","counterparty"} else 40)
            if not data.empty:
                ws.autofilter(3,0,len(data)+3,len(data.columns)-1)
                if sheetname=="Summary":
                    ws.set_column(1,5,20,money)
                    ws.conditional_format(4,5,len(data)+3,5,{"type":"3_color_scale"})
                elif sheetname=="Normalized Data":
                    ws.set_column(6,6,22,money)
                elif sheetname=="Data Quality":
                    ws.set_column(3,3,55,warn)
        if not summary.empty:
            ws=writer.sheets["Summary"]
            chart=book.add_chart({"type":"column"})
            chart.add_series({"name":"Revenue","categories":["Summary",4,0,3+len(summary),0],"values":["Summary",4,1,3+len(summary),1],"fill":{"color":"#0E7490"}})
            chart.add_series({"name":"Expense","categories":["Summary",4,0,3+len(summary),0],"values":["Summary",4,2,3+len(summary),2],"fill":{"color":"#F59E0B"}})
            chart.set_title({"name":"Revenue vs Expense"})
            chart.set_legend({"position":"bottom"})
            chart.set_size({"width":680,"height":330})
            ws.insert_chart("H4",chart)
        # Escaping formula-like user strings is enforced on pre-write data.
    return out.getvalue()

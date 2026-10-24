"""SQLAlchemy persistence. Default SQLite is for a single-machine demonstration only."""
from __future__ import annotations
import os
from datetime import datetime, date, timezone
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, create_engine
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./copilot.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass


class ExactMoney(TypeDecorator[Decimal]):
    """Store cents exactly in SQLite while retaining NUMERIC on PostgreSQL.

    SQLite's NUMERIC affinity may coerce large decimal strings through binary
    floating point.  A non-numeric prefix keeps the local value as text; the
    application already performs all financial aggregation with Decimal.
    """

    impl = Numeric(18, 2)
    cache_ok = True
    quantum = Decimal("0.01")

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(18, 2))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        exact = Decimal(str(value)).quantize(self.quantum)
        return f"D:{exact}" if dialect.name == "sqlite" else exact

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        text = str(value)
        if text.startswith("D:"):
            text = text[2:]
        return Decimal(text).quantize(self.quantum)

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    filename: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    scanned: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    rows: Mapped[list["LedgerRow"]] = relationship(back_populates="batch")

class LedgerRow(Base):
    __tablename__ = "ledger_rows"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_ledger_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), index=True)
    source_sheet: Mapped[str] = mapped_column(String(100))
    source_row: Mapped[int] = mapped_column(Integer)
    document_no: Mapped[str] = mapped_column(String(100), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    counterparty: Mapped[str] = mapped_column(String(200))
    entry_type: Mapped[str] = mapped_column(String(20), index=True)
    amount: Mapped[Decimal] = mapped_column(ExactMoney())
    status: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    batch: Mapped[ImportBatch] = relationship(back_populates="rows")

def init_db() -> None:
    Base.metadata.create_all(engine)

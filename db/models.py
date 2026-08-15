from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Numeric, DateTime, String, Integer
from datetime import datetime

class Base(DeclarativeBase):
    pass

class CandleItem(Base):
    __tablename__ = "candles"
    
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(7), nullable=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(5), nullable=False)
    contract_month:Mapped[str] = mapped_column(String(2), nullable=False)
    contract_year: Mapped[int] = mapped_column(Integer, nullable=False)
    transactions: Mapped[int] = mapped_column(Integer, nullable=False)
    close: Mapped[float] = mapped_column(Numeric(12,4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(12,4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(12,4), nullable=False)
    open: Mapped[float] = mapped_column(Numeric(12,4), nullable=False)
    session_end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    settlement_price: Mapped[float] = mapped_column(Numeric(12,4), nullable=True)
    dollar_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
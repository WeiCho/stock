import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Date, DateTime,
    Boolean, Text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Session

DB_PATH = os.path.expanduser("~/.claude/skills/taiwan-stock/stocks.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class Base(DeclarativeBase):
    pass


class DailyPrice(Base):
    __tablename__ = "daily_price"
    __table_args__ = (UniqueConstraint("symbol", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)


class Institutional(Base):
    __tablename__ = "institutional"
    __table_args__ = (UniqueConstraint("symbol", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    foreign_buy = Column(Float, default=0)   # 外資買賣超（張）
    trust_buy = Column(Float, default=0)     # 投信買賣超（張）
    dealer_buy = Column(Float, default=0)    # 自營商買賣超（張）
    total_buy = Column(Float, default=0)     # 三大法人合計


class IndexData(Base):
    __tablename__ = "index_data"
    __table_args__ = (UniqueConstraint("name", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(20), nullable=False, index=True)  # TAIEX | TPEx
    date = Column(Date, nullable=False, index=True)
    close = Column(Float)
    volume = Column(Float)
    change = Column(Float)


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("symbol", "year", "quarter"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    eps = Column(Float)
    pe = Column(Float)
    roe = Column(Float)
    revenue_mom = Column(Float)   # 月增率 %
    revenue_yoy = Column(Float)   # 年增率 %
    yield_rate = Column(Float)    # 殖利率 %
    debt_ratio = Column(Float)    # 負債比率 %


class NewsCache(Base):
    __tablename__ = "news_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text)
    published_at = Column(DateTime, nullable=False)
    sentiment = Column(String(10))   # positive | neutral | negative
    is_major = Column(Boolean, default=False)
    summary = Column(Text)


class SyncLog(Base):
    """記錄每支股票最後同步時間，用於增量更新判斷。"""
    __tablename__ = "sync_log"
    __table_args__ = (UniqueConstraint("symbol", "data_type"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    data_type = Column(String(20), nullable=False)  # price | institutional | bulk
    last_synced = Column(DateTime, nullable=False, default=datetime.utcnow)


class StockName(Base):
    """股票代碼 ↔ 中文名稱對照表（從 TWSE/TPEx 抓取）。"""
    __tablename__ = "stock_names"
    __table_args__ = (UniqueConstraint("symbol"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    name = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="twse")  # twse | tpex


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)

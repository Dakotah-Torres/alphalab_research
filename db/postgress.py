import os
import dataclasses 
from dotenv import load_dotenv
from .models import CandleItem
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from data_agg.massive_data_provider import FuturesAgg

load_dotenv()
class PostgresDB:
    def __init__(self):
        self.engine = create_engine(os.environ["DATABASE_URL"])
        self.session = sessionmaker(bind=self.engine)
    
    def prep_data_for_insert(self, data: list):
        return [self.future_agg_to_candle(item) for item in data]
    
    def future_agg_to_candle(self, candle: FuturesAgg) -> CandleItem:
        candle_data = dataclasses.asdict(candle)
        
        win_start_seconds = candle.window_start / 1_000_000_000
        candle_data['window_start'] = datetime.fromtimestamp(win_start_seconds, tz=timezone.utc)
        candle_data['session_end_date'] = datetime.strptime(candle.session_end_date, "%Y-%m-%d")
        
        candle_data['contract_month'] = candle.ticker[-2]
        candle_data['symbol'] = candle.ticker[:-2]
        candle_data['contract_year'] = candle_data['session_end_date'].year
        
        return CandleItem(**candle_data)
        
    def bulk_insert_candles(self, candles: list[CandleItem]) -> None:
        if not candles:
            return
        session = self.session()
        try:
            rows = [
                {col.name: getattr(candle, col.name) for col in CandleItem.__table__.columns}
                for candle in candles
            ]
            stmt = pg_insert(CandleItem).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["window_start", "timeframe", "ticker"])
            session.execute(stmt)
            session.commit()
        finally:
            session.close()

    def get_existing_timestamps(self, ticker: str, timeframe: str, start: datetime, end: datetime) -> list[datetime]:
        session = self.session()
        try:
            stmt = (
                select(CandleItem.window_start)
                .where(CandleItem.ticker == ticker)
                .where(CandleItem.timeframe == timeframe)
                .where(CandleItem.window_start >= start)
                .where(CandleItem.window_start <= end)
                .order_by(CandleItem.window_start)
            )
            return [row[0] for row in session.execute(stmt).all()]
        finally:
            session.close()

    def get_candles_df(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        stmt = (
            select(CandleItem)
            .where(CandleItem.symbol == symbol)
            .where(CandleItem.timeframe == timeframe)
            .where(CandleItem.window_start >= start)
            .where(CandleItem.window_start <= end)
            .order_by(CandleItem.window_start)
        )
        return pd.read_sql(stmt, self.engine)
                    
from .models import CandleItem
from datetime import datetime, timezone
from data_agg.massive_data_provider import FuturesAgg
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv




load_dotenv()





class PostgresDB:
    def __init__(self):
        self.engine = create_engine(os.environ["DATABASE_URL"])
        self.session = sessionmaker(bind=self.engine)
    
    def _clean_candle(self, candle: FuturesAgg) -> CandleItem:
        win_start_seconds = candle.window_start / 1_000_000_000
        dt_window = datetime.fromtimestamp(win_start_seconds, tz=timezone.utc)
        dt_ses_end = datetime.strptime(candle.session_end_date, "%Y-%m-%d")
        
        return CandleItem(
            window_start=dt_window,
            timeframe=candle.timeframe,
            ticker=candle.ticker,
            transactions=candle.transactions,
            close=candle.close,
            high=candle.high,
            low=candle.low,
            open=candle.open,
            session_end_date=dt_ses_end,
            settlement_price=candle.settlement_price,
            dollar_volume=candle.dollar_volume,
            volume=candle.volume
        )
        
        
    def bulk_insert_candles(self, candles: list[CandleItem]) -> None:
        session = self.session()
        try:
            session.add_all(candles)
            session.commit()
        finally:
            session.close()
            
            
    def prep_data_for_insert(self, data: dict):
        return [self._clean_candle(item) for item in data.values()]
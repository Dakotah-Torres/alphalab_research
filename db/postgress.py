from .models import CandleItem
from datetime import datetime, timezone
from data_agg.massive_data_provider import FuturesAgg
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import dataclasses 




load_dotenv()





class PostgresDB:
    def __init__(self):
        self.engine = create_engine(os.environ["DATABASE_URL"])
        self.session = sessionmaker(bind=self.engine)
    
    def _clean_candle(self, candle: FuturesAgg) -> CandleItem:
        candle_data = dataclasses.asdict(candle)
        
        win_start_seconds = candle.window_start / 1_000_000_000
        candle_data['window_start'] = datetime.fromtimestamp(win_start_seconds, tz=timezone.utc)
        candle_data['session_end_date'] = datetime.strptime(candle.session_end_date, "%Y-%m-%d")
        
        candle_data['contract_month'] = candle.ticker[-2]
        candle_data['symbol'] = candle.ticker[:-2]
        candle_data['contract_year'] = candle_data['session_end_date'].year
        
        return CandleItem(**candle_data)
        
        
    def bulk_insert_candles(self, candles: list[CandleItem]) -> None:
        session = self.session()
        try:
            session.add_all(candles)
            session.commit()
        finally:
            session.close()
            
            
    def prep_data_for_insert(self, data: list):
        return [self._clean_candle(item) for item in data]
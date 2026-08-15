import os
import json
import dataclasses
import pandas as pd
from dotenv import load_dotenv
from massive import RESTClient
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from db.models import CandleItem

@dataclass
class FuturesAgg:
    ticker: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    dollar_volume: float
    transactions: int
    window_start: int
    session_end_date: str
    settlement_price: Optional[float] = None


load_dotenv()
class MassiveDataProvider():
    def __init__(self, symbol, resolution, limit=2, start:tuple=None, end:tuple =None):
        api_key = os.environ["MASSIVE_API"]
        self.client_con = RESTClient(api_key=api_key, pagination=False)
        
        self.symbol = symbol
        self.ticker = None
        self.resolution = resolution
        self.limit =limit
        self.start = self._date_tuple_to_datetime(start)
        self.end = self._date_tuple_to_datetime(end)
        self._set_contract_ticker()
        
    def _date_tuple_to_datetime(self, date_tuple: tuple) -> datetime:
        year, month, day, hour, minute, second = date_tuple
        dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        epoch_seconds = int(dt.timestamp()*1_000_000_000)
        return epoch_seconds 
    
    def _set_contract_ticker(self) -> str:
        QUARTERLY_MONTHS = {3: "H", 6: "M", 9: "U", 12: "Z"}
        epoch_start_seconds = self.start / 1_000_000_000
        dt = datetime.fromtimestamp(epoch_start_seconds, tz=timezone.utc)
        year = dt.year

        for month in sorted(QUARTERLY_MONTHS):
            if dt.month <= month:
                year_digit = str(year)[-1]
                self.ticker = f"{self.symbol}{QUARTERLY_MONTHS[month]}{year_digit}"
                return

        year_digit = str(year + 1)[-1]
        self.ticker = f"{self.symbol}H{year_digit}" 
    
    def get_futures_bars(self):
        res = self.client_con.list_futures_aggregates(
            ticker=self.ticker,
            resolution=self.resolution,
            window_start_gte=self.start,
            window_start_lte=self.end,
            limit=self.limit
        )
        
        bars = [FuturesAgg(**dataclasses.asdict(item), timeframe=self.resolution) for item in res]
            
        
        return bars
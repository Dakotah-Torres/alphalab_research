from enum import Enum 
from typing import Iterable
import pandas as pd
import numpy as np
class AtrType(Enum):
    SIMP = 1
    WLDR = 2
    ABS_SIMP = 3
    ABS_WLDR = 4


class AverageTrueRange:
    def __init__(self, period, type: AtrType, candles: pd.DataFrame ):
        self.candles = candles.sort_values(by='window_start')
        self.period = period
        self.type = type
        self.true_range_group = []
        
        self.rolling_atr = []

        self.current_candle = None
        self.previous_candle = None
        self.current_row = 0
        self.wild_seed_trig = True
        
        
    def _period_check(self) -> bool:
        return len(self.true_range_group) == self.period
    
    
    def _true_rang(self) -> float:
        if self.previous_candle is None:
            return 0
        
        if self.type in (AtrType.ABS_SIMP, AtrType.ABS_WLDR):
            return self.current_candle['high'] - self.current_candle['low']
        
        return max(
            self.current_candle['high'] - self.current_candle['low'],
            abs(self.current_candle['high'] - self.previous_candle['close']),
            abs(self.current_candle['low'] - self.previous_candle['close'])
        )
            
            
            
    def _update(self):
        self.previous_candle = self.current_candle
        self.current_candle = self.candles.iloc[self.current_row]
        
        if self._period_check():
            self.true_range_group.pop(0)
        
        self.true_range_group.append(self._true_rang())
        
        self.current_row += 1
        

    def _atr(self):
        if not self._period_check():
            return 0
        
        atr = np.average(self.true_range_group)
        return atr
    
    def _wild_atr(self):
        prev_atr = self.rolling_atr[-1]["atr"] if not self.wild_seed_trig else 0
        
        if not self._period_check():
            return 0
        
        if prev_atr == 0:
            self.wild_seed_trig = False
            return self._atr()
        
        w_atr = np.divide(np.multiply(self.period-1, prev_atr) + self.true_range_group[-1], self.period)
        return w_atr
    
    
        
    def get_rolling_atr(self):
        for _ in range(len(self.candles)):
            timestamp = self.candles.iloc[self.current_row]['window_start']
            match self.type:
                case AtrType.SIMP | AtrType.ABS_SIMP:
                    self.rolling_atr.append({"window_start": timestamp, "atr": np.round(self._atr(),2)})
                    self._update()
                    
                case AtrType.WLDR | AtrType.ABS_WLDR:
                    self.rolling_atr.append({"window_start": timestamp, "atr": np.round(self._wild_atr(),2)})
                    self._update()
                    
                case _:
                    raise ValueError(f"Unknown AtrType: {self.type}")
                
        return pd.DataFrame(self.rolling_atr)

import pandas as pd
import numpy as np
import plotly.graph_objects as go


class FairValueGapDetector:
    def __init__(self, candles: pd.DataFrame, threshold: int, time_frame: int = '1min'):
        candles = candles.copy()
        candles['window_start'] = pd.to_datetime(candles['window_start'])
        self.candles = candles.sort_values(by='window_start')
        
        self.first_candle = None
        self.middle_candle = None
        self.last_candle = None
        self.candle_window = []
        self.current_row = 0
        self.threshold = threshold
        self.detected_fvgs = []
        self.time_frame = time_frame
        self.candle_window_init()
    
    def candle_window_init(self):
        agg_rules = {
            'ticker': 'first',             # constant identifier
            'symbol': 'first',             # constant identifier
            'contract_month': 'first',     # constant per contract
            'contract_year': 'first',      # constant per contract
            'transactions': 'sum',         # trade counts add up across the window
            'open': 'first',               # OHLC standard rules
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'session_end_date': 'first',   # constant within a session
            'settlement_price': 'last',    # all null anyway, doesn't matter — 'last' is harmless
            'dollar_volume': 'sum',        # volume-based, sums across window
            'volume': 'sum',
        }
        
        self.candles.sort_values('window_start')
        if self.time_frame: 
            self.candles = self.candles.resample(self.time_frame, on='window_start').agg(agg_rules)
            self.candles['timeframe'] = self.time_frame
            self.candles = self.candles.reset_index() 
            
        for candle in self.candles.iloc[:3].to_dict('records'):
            self.candle_window.append(candle)
            
        self.first_candle, self.middle_candle, self.last_candle = self.candle_window
        self.current_row = len(self.candle_window) - 1
    
    def update(self) -> bool:
        self.current_row += 1
        if self.current_row >= len(self.candles):
            return False
        
        self.candle_window.pop(0)
        next_candle = self.candles.iloc[self.current_row].to_dict()
        self.candle_window.append(next_candle)
        self.first_candle, self.middle_candle, self.last_candle = self.candle_window 
        return True
    
    def fvg_detector(self):
        
        if self.first_candle['high'] < self.last_candle['low']:
            spread = np.abs(self.first_candle['high'] - self.last_candle['low']) * 4
            if spread >= self.threshold:
                fvg = {
                    'high' : self.first_candle['high'],
                    'high_ts' : self.first_candle['window_start'],
                    'low' : self.last_candle['low'],
                    'low_ts' : self.last_candle['window_start'],
                    'type' : 'bullish',
                    'spread' : np.abs(spread),
                }
                self.detected_fvgs.append(fvg)
                
                
                
                
        if self.first_candle['low'] > self.last_candle['high']:
            spread = np.abs(self.last_candle['high'] - self.first_candle['low']) * 4
            if spread >= self.threshold:
                fvg = {
                    'high' : self.last_candle['high'],
                    'high_ts' : self.last_candle['window_start'],
                    'low' : self.first_candle['low'],
                    'low_ts' : self.first_candle['window_start'],
                    'type' : 'bearish',
                    'spread' : np.abs(spread),
                }
                self.detected_fvgs.append(fvg)
    
    def run_detector(self) -> pd.DataFrame:
        self.fvg_detector()
        while self.update():
            self.fvg_detector()
            
        
        return pd.DataFrame(self.detected_fvgs)

    def visualize(self): 
        colors = {'bullish': 'rgba(0, 200, 0, 0.25)', 'bearish': 'rgba(200, 0, 0, 0.25)'}
        extension = pd.Timedelta(minutes=720)
        
        fig = go.Figure(data=[go.Candlestick(
            x=self.candles['window_start'], 
            open=self.candles['open'], 
            high = self.candles['high'],
            low=self.candles['low'],
            close = self.candles['close'],
            name='MNQ'
        )])
        
        fig.update_layout (
            xaxis_rangeslider_visible=False, 
            template='plotly_dark',
            height=700
        )
        
        
        if len(self.detected_fvgs) != 0:
            fvg_df = pd.DataFrame(self.detected_fvgs)  
            
            fvg_df['high_ts'] = pd.to_datetime(fvg_df['high_ts'])
            fvg_df['low_ts'] = pd.to_datetime(fvg_df['low_ts'])
            fvg_df['top'] = fvg_df[['high', 'low']].max(axis=1)
            fvg_df['bottom'] = fvg_df[['high', 'low']].min(axis=1)
            fvg_df['start_ts'] = fvg_df[['high_ts', 'low_ts']].min(axis=1)
        
        for _, row in fvg_df.iterrows():
            fig.add_shape(
                type='rect',
                x0=row['start_ts'],
                x1=row['start_ts'] + extension, 
                y0=row['bottom'],
                y1=row['top'],
                fillcolor=colors[row['type']],
                layer='below',
                line=dict(color="white", width=0.5, dash="dash")
            )
            
        fig.show()
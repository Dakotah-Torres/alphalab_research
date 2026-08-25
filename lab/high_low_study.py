import pandas as pd
import numpy as np
import plotly.graph_objects as go

class HighLowDetector: 
    def __init__(self, candles: pd.DataFrame, window_size: int = 3, time_frame: str = '1min'):
        self.candles = candles.sort_values('window_start') 
        self.window_size = window_size
        self.window = []
        self.detected_highs = []
        self.detected_lows = []
        self.time_frame = time_frame
        self.current_index = window_size - 1
        
        self.current_high_candidate = None
        self.current_high_idx = None
        self.current_low_candidate = None
        self.current_low_idx = None
        
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
        self.candles['window_start'] = pd.to_datetime(self.candles['window_start'])
        self.candles.sort_values('window_start')
        if self.time_frame: 
            self.candles = self.candles.resample(self.time_frame, on='window_start').agg(agg_rules)
            self.candles['timeframe'] = self.time_frame
            self.candles = self.candles.reset_index() 
            self.candles = self.candles.dropna(subset=['high', 'low']).reset_index(drop=True)
            
        for candle in self.candles.iloc[:self.window_size].to_dict('records'):
            self.window.append(candle)

        # NEW: seed both candidates from the initial window
        high_candle = max(self.window, key=lambda c: c['high'])
        self.current_high_candidate = high_candle
        self.current_high_idx = self.window.index(high_candle)

        low_candle = min(self.window, key=lambda c: c['low'])
        self.current_low_candidate = low_candle
        self.current_low_idx = self.window.index(low_candle) 
            
    def update(self):
        self.current_index += 1
        self.window.pop(0)
        self.window.append(self.candles.iloc[self.current_index])
        
        
    def high_low_det(self):
        window_start_idx = self.current_index - self.window_size + 1
        rel_high_idx, high_candle = max(enumerate(self.window), key=lambda pair: pair[1]['high'])
        self.current_high_idx = window_start_idx + rel_high_idx
        self.current_high_candidate = high_candle
        
        
        rel_low_idx, low_candle = min(enumerate(self.window), key=lambda pair: pair[1]['low'])
        self.current_low_idx = window_start_idx + rel_low_idx
        self.current_low_candidate = low_candle
        
    def run_detector(self):
        while self.current_index < len(self.candles) - 1:
            self.update()
            window_start_idx = self.current_index - self.window_size + 1
            
            
            if self.current_high_idx < window_start_idx: 
                self.detected_highs.append(self.current_high_candidate)
                
            
            if self.current_low_idx < window_start_idx:
                self.detected_lows.append(self.current_low_candidate)
                
                    
            
            self.high_low_det()
        
        
        self.detected_highs.append(self.current_high_candidate)
        self.detected_lows.append(self.current_low_candidate)
        
        
        highs_df = pd.DataFrame(self.detected_highs)
        lows_df = pd.DataFrame(self.detected_lows)
        return highs_df, lows_df
    
    def visualize(self, trace: int = 5, max_lines: int = None):
        fig = go.Figure(data=[go.Candlestick(
            x=self.candles['window_start'],
            open=self.candles['open'],
            high=self.candles['high'],
            low=self.candles['low'],
            close=self.candles['close'],
            name='Price'
        )])

        
        chart_end = self.candles['window_start'].iloc[-1]
        
        def build_line_trace(swings, price_key, color, name):
            if max_lines is not None:
                swings = swings[-max_lines:]

            xs, ys = [], []
            for candle in swings:
                start = candle['window_start']
                remaining = chart_end - start        
                end = start + (remaining / 8)  
                xs += [start, end, None]
                ys += [candle[price_key], candle[price_key], None]

            return go.Scatter(
                x=xs, y=ys, mode='lines',
                line=dict(color=color, width=1, dash='dot'),
                name=name, hoverinfo='skip'
            )

        fig.add_trace(build_line_trace(self.detected_highs, 'high', 'red', 'Swing Highs'))
        fig.add_trace(build_line_trace(self.detected_lows, 'low', 'green', 'Swing Lows'))

        fig.update_layout(
            title=f'Swing Highs/Lows (window_size={self.window_size}, timeframe={self.time_frame})',
            xaxis_title='Time',
            yaxis_title='Price',
            xaxis_rangeslider_visible=False
        )

        fig.show()
from data_agg.massive_data_provider import MassiveDataProvider
from db.postgress import PostgresDB

import pandas as pd

def main():
    window_start=(2026, 5, 1, 0, 0, 0)
    window_end = (2026, 5, 1, 1, 0, 0)
    
    db = PostgresDB()
    dp = MassiveDataProvider('MNQ', '1min', start=window_start, end=window_end)
    
    res = dp.get_futures_bars()

    candles = db.prep_data_for_insert(res)
    
    print(candles)
    #db.bulk_insert_candles(candles)
    
    



if __name__ == "__main__":
    main()

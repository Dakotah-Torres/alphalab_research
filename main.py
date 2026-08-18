from data_agg.massive_data_provider import MassiveDataProvider
from db.postgress import PostgresDB
from datetime import datetime, timezone

import pandas as pd

def main():
    
    existing = PostgresDB().get_existing_timestamps("MNQH6", "1min", datetime(2026,1,1,tzinfo=timezone.utc), datetime(2026,6,30,tzinfo=timezone.utc))
    print(len(existing))
    
    



if __name__ == "__main__":
    main()

import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
SYMBOLS = [
    "ITBEES", "SBIETFCON", "INFRAIETF", "SETFNIFBK",
    "HEALTHIETF", "CPSEETF", "BFSI", "MAKEINDIA",
    "COMMOIETF", "FMCGIETF", "AUTOBEES", "ENERGY",
    # "LIQUIDCASE", 
    # "NIFTYBEES"
]
SYMBOL = "ITBEES"
START_DATE = datetime(2020, 1, 4)
END_DATE = datetime(2026, 9, 12)

CHUNK_DAYS = 365  # try 180 if NSE blocks

BASE_URL = "https://www.nseindia.com"
API_URL = "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/"
}

# =========================
# SESSION
# =========================
session = requests.Session()
session.headers.update(HEADERS)
session.get(BASE_URL)  # get cookies

# =========================
# DATE SPLITTER
# =========================
def date_chunks(start, end, chunk_days):
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)

# =========================
# DOWNLOAD LOOP
# =========================

for symbol in SYMBOLS:

    all_data = []

    for start, end in date_chunks(START_DATE, END_DATE, CHUNK_DAYS):

        from_str = start.strftime("%d-%m-%Y")
        to_str = end.strftime("%d-%m-%Y")

        print(f"Downloading {from_str} → {to_str}")

        params = {
            "from": from_str,
            "to": to_str,
            "symbol": symbol,
            "type": "priceVolume",
            "series": "ALL",
            "csv": "true"
        }

        try:
            res = session.get(API_URL, params=params)

            if res.status_code == 200 and "Date" in res.text:
                from io import StringIO
                df = pd.read_csv(StringIO(res.text), encoding='utf-8-sig')
                all_data.append(df)
            else:
                print(f"❌ Failed chunk: {from_str} → {to_str}")

        except Exception as e:
            print(f"❌ Error: {e}")

        time.sleep(1.5)

    # =========================
    # MERGE
    # =========================
    final_df = pd.concat(all_data, ignore_index=True)

    # Clean + sort
    final_df.columns = final_df.columns.str.strip()
    final_df['Date'] = pd.to_datetime(final_df['Date'])
    final_df = final_df.sort_values('Date').drop_duplicates(subset=['Date'])

    # Save
    file_name = f"{symbol}_FULL.csv"
    final_df.to_csv(file_name, index=False)

    print(f"\n✅ Saved full dataset: {file_name}")

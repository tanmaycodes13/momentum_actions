#!/usr/bin/env python3
"""Download two years of NSE ETF data and produce the current allocation."""

from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


SYMBOLS = [
    "ITBEES",
    "SBIETFCON",
    "INFRAIETF",
    "SETFNIFBK",
    "HEALTHIETF",
    "CPSEETF",
    "BFSI",
    "MAKEINDIA",
    "COMMOIETF",
    "FMCGIETF",
    "AUTOBEES",
    "ENERGY",
]

LOOKBACK_TRADING_DAYS = 90
TOP_N = 5
CHUNK_DAYS = 180
BASE_URL = "https://www.nseindia.com"
API_URL = f"{BASE_URL}/api/historicalOR/generateSecurityWiseHistoricalData"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE_URL}/",
}


def india_today() -> date:
    india_timezone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(india_timezone).date()


def date_chunks(start: date, end: date):
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(BASE_URL, timeout=30)
    response.raise_for_status()
    return session


def download_symbol(
    session: requests.Session, symbol: str, start: date, end: date
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for chunk_start, chunk_end in date_chunks(start, end):
        params = {
            "from": chunk_start.strftime("%d-%m-%Y"),
            "to": chunk_end.strftime("%d-%m-%Y"),
            "symbol": symbol,
            "type": "priceVolume",
            "series": "ALL",
            "csv": "true",
        }

        for attempt in range(1, 4):
            try:
                response = session.get(API_URL, params=params, timeout=60)
                response.raise_for_status()
                if "Date" not in response.text:
                    raise RuntimeError("NSE response did not contain CSV price data")
                frames.append(pd.read_csv(StringIO(response.text), encoding="utf-8-sig"))
                break
            except (requests.RequestException, RuntimeError) as exc:
                if attempt == 3:
                    raise RuntimeError(
                        f"Could not download {symbol} for {chunk_start} to {chunk_end}"
                    ) from exc
                time.sleep(3 * attempt)

        time.sleep(1.5)

    if not frames:
        raise RuntimeError(f"NSE returned no data for {symbol}")

    data = pd.concat(frames, ignore_index=True)
    data.columns = data.columns.str.strip()
    if "Date" not in data.columns:
        raise RuntimeError(f"Downloaded data for {symbol} has no Date column")
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    return data.dropna(subset=["Date"]).sort_values("Date").drop_duplicates("Date")


def clean_price_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def build_price_frame(downloads: dict[str, pd.DataFrame]) -> pd.DataFrame:
    prices: dict[str, pd.Series] = {}
    for symbol, data in downloads.items():
        normalized = data.copy()
        normalized.columns = (
            normalized.columns.str.strip()
            .str.lower()
            .str.replace(r"\s+", " ", regex=True)
        )
        if "close price" not in normalized.columns:
            raise RuntimeError(f"Downloaded data for {symbol} has no Close Price column")
        normalized = normalized.set_index(pd.to_datetime(normalized["date"]))
        prices[symbol] = clean_price_series(normalized["close price"])

    # This matches the notebook: calculate only on dates available for every ETF.
    return pd.DataFrame(prices).sort_index().dropna()


def calculate_allocation(prices: pd.DataFrame) -> tuple[pd.Timestamp, pd.DataFrame]:
    if len(prices) <= LOOKBACK_TRADING_DAYS:
        raise RuntimeError(
            f"Only {len(prices)} common trading days were downloaded; "
            f"more than {LOOKBACK_TRADING_DAYS} are required"
        )

    momentum = prices / prices.shift(LOOKBACK_TRADING_DAYS) - 1
    as_of = momentum.dropna(how="all").index[-1]
    ranked = momentum.loc[as_of].dropna().sort_values(ascending=False)
    if ranked.empty:
        raise RuntimeError("No momentum values could be calculated")

    ranking = ranked.rename("momentum").to_frame()
    ranking.index.name = "symbol"
    ranking["rank"] = range(1, len(ranking) + 1)
    ranking["weight"] = 0.0

    # Preserve the notebook's rule: invest equally in the top five when the
    # strongest ETF has positive 90-trading-day momentum; otherwise hold cash.
    if ranked.iloc[0] > 0:
        selected = ranked.index[:TOP_N]
        ranking.loc[selected, "weight"] = 1.0 / TOP_N

    ranking["selected"] = ranking["weight"] > 0
    return as_of, ranking.reset_index()[
        ["rank", "symbol", "momentum", "weight", "selected"]
    ]


def write_outputs(
    output_dir: Path,
    run_date: date,
    as_of: pd.Timestamp,
    ranking: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    allocation = ranking.loc[ranking["selected"], ["symbol", "weight", "momentum"]]
    if allocation.empty:
        allocation = pd.DataFrame(
            [{"symbol": "CASH", "weight": 1.0, "momentum": pd.NA}]
        )

    allocation.to_csv(output_dir / "todays_allocation.csv", index=False)
    ranking.to_csv(output_dir / "momentum_ranking.csv", index=False)

    rows = "\n".join(
        f"| {row.symbol} | {row.weight:.0%} | "
        + ("N/A" if pd.isna(row.momentum) else f"{row.momentum:.2%}")
        + " |"
        for row in allocation.itertuples(index=False)
    )
    report = f"""# ETF momentum allocation

- Workflow run date (India): {run_date.isoformat()}
- Latest common NSE trading date: {as_of.date().isoformat()}
- Momentum lookback: {LOOKBACK_TRADING_DAYS} trading days
- Allocation rule: top {TOP_N}, equal weighted, when strongest momentum is positive

| Symbol | Weight | 90-day momentum |
|---|---:|---:|
{rows}

The complete ranking is available in `momentum_ranking.csv`.
"""
    (output_dir / "allocation_report.md").write_text(report, encoding="utf-8")

    github_summary = Path("/tmp/github-step-summary.md")
    github_summary.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("momentum_actions/output")
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("/tmp/momentum-actions-data"),
        help="Temporary destination for downloaded CSV files",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="Optional YYYY-MM-DD override, useful for reproducible testing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    end = args.end_date or india_today()
    start = end - timedelta(days=2 * 365)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {start} through {end} from NSE")
    session = make_session()
    downloads: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        print(f"Downloading {symbol}...")
        data = download_symbol(session, symbol, start, end)
        data.to_csv(args.data_dir / f"{symbol}_FULL.csv", index=False)
        downloads[symbol] = data

    prices = build_price_frame(downloads)
    as_of, ranking = calculate_allocation(prices)
    write_outputs(args.output_dir, end, as_of, ranking)
    print(f"Allocation generated using NSE data through {as_of.date()}")


if __name__ == "__main__":
    main()

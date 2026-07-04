#!/usr/bin/env python3
"""Read uploaded NSE ETF data and produce the current allocation."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

LOOKBACK_TRADING_DAYS = 90
TOP_N = 5


def india_today() -> date:
    india_timezone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(india_timezone).date()


def load_uploaded_data(
    data_dir: Path, start: date, end: date
) -> dict[str, pd.DataFrame]:
    files = sorted(data_dir.glob("*_FULL.csv"))
    if not files:
        raise RuntimeError(f"No *_FULL.csv files found in {data_dir}")

    datasets: dict[str, pd.DataFrame] = {}
    for path in files:
        symbol = path.stem[:-5]
        data = pd.read_csv(path, encoding="utf-8-sig")
        data.columns = data.columns.str.strip()
        missing = {"Date", "Close Price"}.difference(data.columns)
        if missing:
            raise RuntimeError(f"{path} is missing columns: {sorted(missing)}")

        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        data = data.dropna(subset=["Date"])
        data = data.loc[
            (data["Date"].dt.date >= start) & (data["Date"].dt.date <= end)
        ].sort_values("Date").drop_duplicates("Date")
        if len(data) <= LOOKBACK_TRADING_DAYS:
            print(
                f"Skipping {symbol}: only {len(data)} rows were available by {end}; "
                f"at least {LOOKBACK_TRADING_DAYS + 1} are required"
            )
            continue

        datasets[symbol] = data
        print(f"Loaded {symbol}: {len(data)} rows through {data['Date'].max().date()}")

    if not datasets:
        raise RuntimeError(
            f"No ETF had enough history to calculate momentum as of {end}"
        )
    return datasets


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
            raise RuntimeError(f"Uploaded data for {symbol} has no Close Price column")
        normalized = normalized.set_index(pd.to_datetime(normalized["date"]))
        prices[symbol] = clean_price_series(normalized["close price"])

    # This matches the notebook: calculate only on dates available for every ETF.
    return pd.DataFrame(prices).sort_index().dropna()


def calculate_allocation(prices: pd.DataFrame) -> tuple[pd.Timestamp, pd.DataFrame]:
    if len(prices) <= LOOKBACK_TRADING_DAYS:
        raise RuntimeError(
            f"Only {len(prices)} common trading days were available; "
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

    # Strict absolute-momentum filter: never allocate to a negative-momentum ETF.
    selected = ranked[ranked > 0].index[:TOP_N]
    if len(selected):
        ranking.loc[selected, "weight"] = 1.0 / len(selected)

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
- Allocation rule: up to {TOP_N} positive-momentum ETFs, equal weighted

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
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing uploaded *_FULL.csv files",
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
    print(f"Loading uploaded data for {start} through {end}")
    downloads = load_uploaded_data(args.data_dir, start, end)

    prices = build_price_frame(downloads)
    as_of, ranking = calculate_allocation(prices)
    write_outputs(args.output_dir, end, as_of, ranking)
    print(f"Allocation generated using uploaded data through {as_of.date()}")


if __name__ == "__main__":
    main()

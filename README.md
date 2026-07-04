# ETF allocation GitHub Action

This automation reads the uploaded `data/*_FULL.csv` NSE ETF files, uses the
trailing two calendar years, calculates 90-trading-day momentum, and opens a
pull request with the current top-five equal-weight allocation.

## Set up

1. Commit and push this repository. The workflow is already located at
   `.github/workflows/daily-allocation.yml`.
2. In the GitHub repository, open **Settings > Actions > General > Workflow
   permissions**, select **Read and write permissions**, and enable **Allow
   GitHub Actions to create and approve pull requests**.
3. Open the repository's **Actions** tab, choose **ETF daily allocation PR**,
   and click **Run workflow**. Enter an optional date in `YYYY-MM-DD` format,
   or leave it blank to use today's date in India.

The selected date is the data cutoff. For example, `2026-06-15` ignores every
CSV row after that date and calculates the allocation from the preceding two
calendar years. If the selected date is a weekend or market holiday, the latest
common trading date before it is used.

The action creates or updates a branch named `actions/etf-allocation-YYYY-MM-DD`
and opens a PR containing:

- `output/todays_allocation.csv`
- `output/momentum_ranking.csv`
- `output/allocation_report.md`

The ETF CSV files in `data/` are the strategy's tradeable universe. Add or
remove a `*_FULL.csv` file to change that universe.

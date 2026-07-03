# ETF allocation GitHub Action

This automation downloads the trailing two calendar years for the configured
NSE ETFs, calculates 90-trading-day momentum, and opens a pull request with the
current top-five equal-weight allocation.

## Set up

1. Commit and push this repository. The workflow is already located at
   `.github/workflows/daily-allocation.yml`.
2. In the GitHub repository, open **Settings > Actions > General > Workflow
   permissions**, select **Read and write permissions**, and enable **Allow
   GitHub Actions to create and approve pull requests**.
3. Open the repository's **Actions** tab, choose **ETF daily allocation PR**,
   and click **Run workflow**.

The action creates or updates a branch named `actions/etf-allocation-YYYY-MM-DD`
and opens a PR containing:

- `output/todays_allocation.csv`
- `output/momentum_ranking.csv`
- `output/allocation_report.md`

Raw market data is kept temporarily on the runner and is not committed.

If NSE blocks the GitHub-hosted runner's IP address, rerun the workflow. NSE's
public endpoints occasionally reject automated cloud traffic.

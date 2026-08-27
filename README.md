# Trading Signals Dashboard

A fully static, professional trading analytics dashboard that visualizes trading signals stored as CSV files in this repository. No backend required: the site reads the CSVs live via the GitHub API directly in the browser.

## How it works

- One CSV file per signal date (e.g. `2026-06-14.csv`), stored anywhere in this repository.
- Each CSV is published with new trade calls and updated daily until all trades are closed.
- While a trade is open, daily columns are appended: `YYYY-MM-DD_MaxProfit` and `YYYY-MM-DD_MaxLoss`.
- The dashboard automatically discovers all `.csv` files, parses the dynamic date columns, and computes all analytics client-side.
- New or modified CSVs are picked up automatically on the next page load. **No redeploy is needed for data changes.**

## CSV format

| Column | Description |
|---|---|
| `Symbol` | Instrument symbol |
| `Entry` | Entry price |
| `SL` | Stop loss price |
| `TP` | Target price |
| `Status` | `Open`, `TP Hit`, `SL Hit`, or `Closed` |
| `Exit Price` | Filled when the trade closes |
| `Exit Date` | Filled when the trade closes |
| `YYYY-MM-DD_MaxProfit` | Max favorable move (%) on that day (appended daily while open) |
| `YYYY-MM-DD_MaxLoss` | Max adverse move (%) on that day (appended daily while open) |

The signal date is taken from the filename (`YYYY-MM-DD.csv`).

## Pages

- `index.html` - KPI dashboard, active signal summary, open-trade age chart, latest trading days (incremental loading), performance charts, analytics, leaderboards, repository activity, transparency section.
- `active-signals.html` - Live watchlist of all open trades with search, sorting, filtering, pagination, and CSV export.
- `signals.html` - Browser for every CSV file with per-file statistics and expandable signal tables.
- `sl-hits.html` - Stop loss hits with reentry points analysis.
- Clicking any trade opens a detail modal with daily performance table and an interactive Max Profit / Max Loss progression chart.

## Deployment (GitHub Pages)

1. Push to the `main` branch. The included `.github/workflows/daily-process.yml` processes signals daily and deploys to `gh-pages` branch.
2. Enable GitHub Pages: Settings → Pages → Source: **Deploy from branch** → `gh-pages` / root
3. After the first successful workflow run, the site is available at:
   `https://faizjio7011-code.github.io/trade_signals/`
4. The repository must be **public** so the GitHub API can be read anonymously by visitors' browsers.

## Configuration

All data-source settings live at the top of `app.js` in the `CONFIG` object:

```js
const CONFIG = {
  source: 'github',
  csvFolder: 'signals/',
  slHitsFolder: 'sl_hits/',
  github: { owner: 'faizjio7011-code', repo: 'trade_signals', branch: 'main' },
  concurrency: 8,
  cachePrefix: 'sigcache:v1:',
};
```

## Daily Processing

The GitHub Action (`.github/workflows/daily-process.yml`) runs daily:
1. Reads `orderbook/*.csv` files
2. Fetches price data via yfinance
3. Calculates daily Max Profit/Loss, TP/SL hits
4. Generates `signals/*.csv` with daily performance columns
5. Creates `sl_hits/*.csv` with reentry points (next same-direction candle after SL hit)
6. Commits updates and deploys to GitHub Pages

## Performance

- File contents are cached in `localStorage`, keyed by each file's git blob SHA, so unchanged CSVs are never re-downloaded.
- Files are fetched with bounded concurrency; tables are paginated and the homepage loads day sections incrementally.

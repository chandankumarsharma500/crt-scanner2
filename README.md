# CRT Scanner 2 — NSE Equities

Standalone Streamlit scanner based on the supplied TradingView Pine Script:

**CRT Setup Scanner (M1 CRT + M2 Sweep → M3 Entry)**

## What it does
- Fetches the current NSE cash-equity universe from the NSE equity list and filters Series EQ.
- Downloads daily OHLC history for NSE symbols through Yahoo Finance (SYMBOL.NS).
- Implements monthly M1/M2 CRT bias, rolling liquidity sweep, pivot break, ATR displacement, entry, stop-loss, T1/T2, invalidation, and the three setup stages.
- Shows a dashboard with BUY/SELL setups, M1/M2 levels, LTP, Entry, SL, T1 and T2.
- Exports results as CSV and reports symbols where market data could not be fetched.
- Defaults to scanning the full downloaded NSE Series EQ list; smaller test batches are available in the sidebar.

## Run locally
Python 3.10+ recommended.

```bash
git clone https://github.com/chandankumarsharma500/crt-scanner2.git
cd crt-scanner2
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Open https://share.streamlit.io/.
2. Connect GitHub and select chandankumarsharma500/crt-scanner2.
3. Select branch main.
4. Set Main file path to app.py.
5. Deploy.

## Strategy defaults from the Pine Script
| Setting | Default |
|---|---:|
| ATR length | 14 |
| Displacement | 1.2 × ATR |
| Pivot left / right | 3 / 3 |
| Sweep lookback | 10 daily bars |
| Entry signal lookback | 3 daily bars |
| Confirmed-only signal search | Enabled |

### Stage meanings
- **Stage 1 — Wait Sweep:** M2 defines a bullish or bearish CRT bias relative to M1.
- **Stage 2 — Wait CHoCH:** The rolling prior high/low is swept and the candle closes back inside.
- **Stage 3 — BUY / SELL:** A displacement candle breaks the last confirmed pivot, falling back to the 5-day high/low when no pivot is available.

## Important data and logic notes
- The scanner is designed for daily candles, as in the supplied Pine script's request.security(..., D, ...).
- Confirmed-only mode keeps bias/LTP context on the latest bar while shifting the historical sweep and entry search back one daily candle, following the Pine script's _off handling.
- ATR uses Wilder RMA smoothing, as Pine's ta.atr() does.
- NSE's published symbol list and Yahoo Finance ticker coverage are not identical. Some listed shares may have no Yahoo Finance history, and provider throttling or missing candles can reduce successful coverage. Failed symbols are listed in the app.
- A full-universe run may be slow. Use a smaller batch first to validate data access.
- The original Pine script's alert() calls are TradingView alerts. This standalone build presents signals in the dashboard and CSV; it does not place orders or send Telegram/email alerts.
- Validate scanner output against TradingView for sample symbols before making trading decisions. This is a research tool, not investment advice.

## Project files
- app.py — Streamlit dashboard and run controls.
- scanner.py — CRT scan calculations based on the Pine strategy.
- universe.py — NSE symbol list and Yahoo Finance history downloads.
- requirements.txt — Python dependencies.

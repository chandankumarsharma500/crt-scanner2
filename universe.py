"""Market symbol universes and Yahoo Finance daily history loader."""
from __future__ import annotations
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
import yfinance as yf

NSE_CSV_URLS = [
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}

# Yahoo Finance symbols are used as a practical cross-market data source.
# Non-NSE universes are curated liquid watchlists, not every listed security.
MARKET_WATCHLISTS = {
    "BSE – Indian Stocks": {
        "type": "BSE",
        "symbols": ["RELIANCE.BO","TCS.BO","HDFCBANK.BO","ICICIBANK.BO","INFY.BO","ITC.BO","SBIN.BO","BHARTIARTL.BO","LT.BO","AXISBANK.BO","KOTAKBANK.BO","HINDUNILVR.BO","BAJFINANCE.BO","MARUTI.BO","TATAMOTORS.BO","SUNPHARMA.BO","WIPRO.BO","TATASTEEL.BO","NTPC.BO","POWERGRID.BO"]
    },
    "NIFTY / BANKNIFTY – Indices": {
        "type": "INDEX",
        "symbols": ["^NSEI","^NSEBANK","^BSESN","^CNXIT"]
    },
    "MCX – Commodities": {
        "type": "MCX",
        "symbols": ["GOLD=F","SILVER=F","CL=F","NG=F","HG=F","PL=F"]
    },
    "Forex – Currency": {
        "type": "FOREX",
        "symbols": ["USDINR=X","EURINR=X","GBPINR=X","JPYINR=X","EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X","USDCHF=X"]
    },
    "Crypto – Bitcoin एवं अन्य": {
        "type": "CRYPTO",
        "symbols": ["BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD","ADA-USD","DOGE-USD","TRX-USD","AVAX-USD","LINK-USD"]
    },
    "NASDAQ / NYSE – US Stocks": {
        "type": "US",
        "symbols": ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","NFLX","AMD","JPM","V","WMT","LLY","XOM","COST","ORCL","KO","DIS","BAC"]
    },
}

def load_nse_symbols() -> pd.DataFrame:
    errors = []
    for url in NSE_CSV_URLS:
        try:
            response = requests.get(url, headers=HEADERS, timeout=25)
            response.raise_for_status()
            frame = pd.read_csv(io.BytesIO(response.content))
            frame.columns = [str(c).strip().upper() for c in frame.columns]
            if "SYMBOL" not in frame:
                continue
            if "SERIES" in frame:
                frame = frame[frame["SERIES"].astype(str).str.strip().eq("EQ")]
            frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip()
            frame = frame[frame["SYMBOL"].ne("") & frame["SYMBOL"].ne("nan")]
            return frame.drop_duplicates("SYMBOL").sort_values("SYMBOL").reset_index(drop=True)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("NSE symbol list download failed. " + " | ".join(errors))

def download_market_histories(items: list[tuple[str, str]], period: str = "3y",
                              workers: int = 8, progress_callback=None):
    histories, errors = {}, {}
    def fetch(item):
        label, ticker = item
        try:
            data = yf.download(ticker, period=period, interval="1d", auto_adjust=False,
                               progress=False, threads=False, timeout=20)
            if data is None or data.empty:
                return label, None, f"No daily data returned for {ticker}"
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return label, data, None
        except Exception as exc:
            return label, None, str(exc)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {pool.submit(fetch, item): item[0] for item in items}
        for count, future in enumerate(as_completed(futures), start=1):
            label, data, error = future.result()
            if data is not None:
                histories[label] = data
            else:
                errors[label] = error or "Unknown data error"
            if progress_callback:
                progress_callback(count, len(items), label)
    return histories, errors

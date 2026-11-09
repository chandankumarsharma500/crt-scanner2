"""NSE cash-equity universe and Yahoo Finance history loader."""
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

def load_nse_symbols() -> pd.DataFrame:
    """Fetch current NSE listed equity symbols (Series EQ only)."""
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

def _download_one(symbol: str, period: str):
    ticker = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    try:
        data = yf.download(ticker, period=period, interval="1d", auto_adjust=False,
                           progress=False, threads=False, timeout=20)
        if data is None or data.empty:
            return symbol, None, "No daily data returned"
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return symbol, data, None
    except Exception as exc:
        return symbol, None, str(exc)

def download_histories(symbols: list[str], period: str = "3y", workers: int = 8, progress_callback=None):
    histories, errors = {}, {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        futures = {pool.submit(_download_one, s, period): s for s in symbols}
        for count, future in enumerate(as_completed(futures), start=1):
            symbol, data, error = future.result()
            if data is not None: histories[symbol] = data
            else: errors[symbol] = error or "Unknown download error"
            if progress_callback: progress_callback(count, len(symbols), symbol)
    return histories, errors

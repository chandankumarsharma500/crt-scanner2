"""Daily-timeframe implementation of the user's Pine Script CRT setup scanner."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import math
import numpy as np
import pandas as pd

@dataclass
class ScanResult:
    symbol: str
    ltp: float | None = None
    bias: str = "Neutral"
    stage: int = 0
    stage_text: str = "-"
    entry: float | None = None
    sl: float | None = None
    t1: float | None = None
    t2: float | None = None
    invalidation: float | None = None
    m1_high: float | None = None
    m1_low: float | None = None
    m2_high: float | None = None
    m2_low: float | None = None
    m2_close: float | None = None
    signal: str = ""
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _pine_pivots(series: pd.Series, left: int, right: int, high_pivot: bool) -> pd.Series:
    values = series.to_numpy(dtype=float)
    n = len(values)
    confirmed = np.full(n, np.nan)
    for i in range(left + right, n):
        pivot_at = i - right
        window = values[pivot_at-left:pivot_at+right+1]
        candidate = values[pivot_at]
        if not np.isfinite(candidate) or not np.isfinite(window).all():
            continue
        extreme = np.max(window) if high_pivot else np.min(window)
        if candidate == extreme:
            confirmed[i] = candidate
    return pd.Series(confirmed, index=series.index).ffill()

def _monthly_context(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    month = out.index.to_period("M")
    cur_h = cur_l = m1_h = m1_l = m2_h = m2_l = m2_c = np.nan
    m_start = m2_start = pd.NaT
    vals = {k: [] for k in ("m1H", "m1L", "m2H", "m2L", "m2C", "m2Start")}
    for i, (ts, row) in enumerate(out.iterrows()):
        new_month = i == 0 or month[i] != month[i-1]
        if new_month:
            if i == 0:
                m_start = ts
                cur_h, cur_l = float(row.High), float(row.Low)
            else:
                m1_h, m1_l = m2_h, m2_l
                m2_h, m2_l = cur_h, cur_l
                m2_c = float(out.Close.iloc[i-1])
                m2_start = m_start
                m_start = ts
                cur_h, cur_l = float(row.High), float(row.Low)
        else:
            cur_h = max(cur_h, float(row.High))
            cur_l = min(cur_l, float(row.Low))
        vals["m1H"].append(m1_h); vals["m1L"].append(m1_l)
        vals["m2H"].append(m2_h); vals["m2L"].append(m2_l)
        vals["m2C"].append(m2_c); vals["m2Start"].append(m2_start)
    for key, value in vals.items():
        out[key] = value
    return out

def scan_symbol(symbol: str, history: pd.DataFrame, atr_len: int = 14,
                displacement_atr: float = 1.2, pivot_left: int = 3,
                pivot_right: int = 3, sweep_lookback: int = 10,
                entry_lookback: int = 3, confirmed_only: bool = True) -> ScanResult:
    result = ScanResult(symbol=symbol)
    if history is None or history.empty:
        return result
    df = history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns):
        return result
    df = df.dropna(subset=list(required)).sort_index()
    if len(df) < max(atr_len + 5, sweep_lookback + pivot_left + pivot_right + 5):
        return result
    df = _monthly_context(df)
    prev_close = df.Close.shift(1)
    tr = pd.concat([df.High-df.Low, (df.High-prev_close).abs(), (df.Low-prev_close).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/atr_len, adjust=False, min_periods=atr_len).mean()
    df["pl"] = df.Low.rolling(sweep_lookback, min_periods=sweep_lookback).min()
    df["ph"] = df.High.rolling(sweep_lookback, min_periods=sweep_lookback).max()
    df["hh5"] = df.High.rolling(5, min_periods=5).max()
    df["ll5"] = df.Low.rolling(5, min_periods=5).min()
    df["lastPH"] = _pine_pivots(df.High, pivot_left, pivot_right, True)
    df["lastPL"] = _pine_pivots(df.Low, pivot_left, pivot_right, False)
    off = 1 if confirmed_only else 0
    cur = len(df)-1-off
    if cur < 1:
        return result
    row = df.iloc[cur]
    result.ltp = _num(row.Close)
    m1h, m1l = _num(row.m1H), _num(row.m1L)
    m2h, m2l, m2c = _num(row.m2H), _num(row.m2L), _num(row.m2C)
    result.m1_high, result.m1_low = m1h, m1l
    result.m2_high, result.m2_low, result.m2_close = m2h, m2l, m2c
    if None in (m1h, m1l, m2h, m2l, m2c):
        return result
    bias = 1 if m2l < m1l and m2c > m1l else (-1 if m2h > m1h and m2c < m1h else 0)
    result.bias = "Bullish" if bias == 1 else ("Bearish" if bias == -1 else "Neutral")
    close_now, m2_start = float(row.Close), row.m2Start
    if pd.isna(m2_start):
        return result
    sig = 0
    entry = sl = t1 = t2 = inv = None
    found = False
    if bias == 1 and close_now > m1l:
        for c in range(entry_lookback):
            for s in range(c+1, c+1+sweep_lookback):
                cc, ss = cur-c, cur-s
                prior_idx = ss-1
                if prior_idx < 0 or cc < 0 or ss < 0:
                    continue
                prior_low = _num(df.pl.iloc[prior_idx])
                if prior_low is None:
                    continue
                sweep = (float(df.Low.iloc[ss]) < prior_low and float(df.Close.iloc[ss]) > prior_low and df.index[ss] >= m2_start)
                if sweep:
                    lvl = _num(df.lastPH.iloc[ss])
                    if lvl is None:
                        lvl = _num(df.hh5.iloc[prior_idx])
                    body = float(df.Close.iloc[cc])-float(df.Open.iloc[cc])
                    atr = _num(df.atr.iloc[cc])
                    if lvl is not None and atr is not None and float(df.Close.iloc[cc]) > lvl and body >= displacement_atr*atr:
                        sig, entry, sl = 1, float(df.Close.iloc[cc]), float(df.Low.iloc[ss])
                        t1, found = entry+2*(entry-sl), True
                        break
            if found: break
    elif bias == -1 and close_now < m1h:
        for c in range(entry_lookback):
            for s in range(c+1, c+1+sweep_lookback):
                cc, ss = cur-c, cur-s
                prior_idx = ss-1
                if prior_idx < 0 or cc < 0 or ss < 0:
                    continue
                prior_high = _num(df.ph.iloc[prior_idx])
                if prior_high is None:
                    continue
                sweep = (float(df.High.iloc[ss]) > prior_high and float(df.Close.iloc[ss]) < prior_high and df.index[ss] >= m2_start)
                if sweep:
                    lvl = _num(df.lastPL.iloc[ss])
                    if lvl is None:
                        lvl = _num(df.ll5.iloc[prior_idx])
                    body = float(df.Open.iloc[cc])-float(df.Close.iloc[cc])
                    atr = _num(df.atr.iloc[cc])
                    if lvl is not None and atr is not None and float(df.Close.iloc[cc]) < lvl and body >= displacement_atr*atr:
                        sig, entry, sl = -1, float(df.Close.iloc[cc]), float(df.High.iloc[ss])
                        t1, found = entry-2*(sl-entry), True
                        break
            if found: break
    stage = 0
    if bias == 1 and close_now > m1l:
        stage, inv, t2 = 1, m1l, m2h
    elif bias == -1 and close_now < m1h:
        stage, inv, t2 = 1, m1h, m2l
    if sig != 0:
        stage = 3
    elif stage == 1:
        for s in range(sweep_lookback):
            ss, prior_idx = cur-s, cur-s-1
            if prior_idx < 0: continue
            if bias == 1:
                prior = _num(df.pl.iloc[prior_idx])
                if prior is not None and float(df.Low.iloc[ss]) < prior and float(df.Close.iloc[ss]) > prior and df.index[ss] >= m2_start:
                    stage, sl = 2, float(df.Low.iloc[ss]); break
            else:
                prior = _num(df.ph.iloc[prior_idx])
                if prior is not None and float(df.High.iloc[ss]) > prior and float(df.Close.iloc[ss]) < prior and df.index[ss] >= m2_start:
                    stage, sl = 2, float(df.High.iloc[ss]); break
    result.stage = stage
    result.stage_text = ("BUY" if bias == 1 else "SELL") if stage == 3 else ("Wait CHoCH" if stage == 2 else ("Wait Sweep" if stage == 1 else "-"))
    result.entry, result.sl, result.t1, result.t2, result.invalidation = entry, sl, t1, t2, inv
    result.signal = "BUY" if sig == 1 else ("SELL" if sig == -1 else "")
    return result

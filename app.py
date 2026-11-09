from __future__ import annotations
import pandas as pd
import streamlit as st
from scanner import scan_symbol
from universe import load_nse_symbols, download_histories

st.set_page_config(page_title="CRT Scanner 2 · NSE", page_icon="📈", layout="wide")
st.title("📈 CRT Scanner 2 — NSE Equities")
st.caption("Daily timeframe · M1 CRT + M2 Sweep → M3 Entry · Based on your Pine Script rules")

with st.sidebar:
    st.header("Scanner settings")
    period = st.selectbox("Historical data", ["3y", "5y", "2y"], index=0)
    batch_size = st.selectbox("Symbols per run", ["All NSE stocks", 500, 1000, 2000], index=0)
    workers = st.slider("Parallel downloads", 2, 12, 8)
    st.divider()
    st.subheader("CRT strategy")
    atr_len = st.number_input("ATR Length", 1, 100, 14)
    disp = st.number_input("Displacement × ATR", 0.1, 10.0, 1.2, 0.1)
    piv_l = st.number_input("Pivot Left", 1, 20, 3)
    piv_r = st.number_input("Pivot Right", 1, 20, 3)
    sweep_lb = st.number_input("Sweep Lookback (days)", 3, 60, 10)
    entry_lb = st.number_input("Entry valid (daily candles)", 1, 10, 3)
    confirmed = st.checkbox("Only confirmed / closed daily candles", value=True)
    only_ready = st.checkbox("Show only setup-ready symbols", value=True)

@st.cache_data(ttl=3600, show_spinner=False)
def get_universe():
    return load_nse_symbols()

try:
    universe = get_universe()
    st.success(f"NSE equity universe loaded: {len(universe):,} symbols (Series EQ)")
except Exception as exc:
    st.error(f"Could not load the live NSE symbol list: {exc}")
    st.stop()

symbols = universe["SYMBOL"].tolist()
if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "scan_errors" not in st.session_state: st.session_state.scan_errors = {}

left, right = st.columns([1, 3])
with left:
    start = st.button("▶ Scan NSE stocks", type="primary", use_container_width=True)
with right:
    st.info("Default scans the entire current NSE Series EQ list. Large scans can take time; Yahoo Finance may throttle or omit some symbols.")

if start:
    selected = symbols if batch_size == "All NSE stocks" else symbols[:int(batch_size)]
    progress = st.progress(0, text="Starting market-data downloads…")
    status = st.empty()
    def update_progress(done, total, symbol):
        progress.progress(done / max(total, 1), text=f"Downloaded {done:,}/{total:,} · {symbol}")
        status.caption(f"Processing NSE universe: {done:,} of {total:,}")
    histories, errors = download_histories(selected, period, workers, update_progress)
    results = []
    for symbol, history in histories.items():
        try:
            result = scan_symbol(symbol, history, int(atr_len), float(disp), int(piv_l),
                                 int(piv_r), int(sweep_lb), int(entry_lb), bool(confirmed))
            results.append(result.to_dict())
        except Exception as exc:
            errors[symbol] = f"Scanner error: {exc}"
    st.session_state.scan_results = pd.DataFrame(results)
    st.session_state.scan_errors = errors
    st.session_state.scanned_count = len(selected)
    st.session_state.success_count = len(histories)
    progress.empty(); status.empty()
    st.toast(f"Scan complete: {len(results)} symbols evaluated")

data = st.session_state.scan_results
if data is not None:
    if data.empty:
        st.warning("No symbols produced usable daily data in this run.")
    else:
        ready = data[data["stage"] >= 1].copy()
        swept = data[data["stage"] == 2]
        entries = data[data["stage"] == 3]
        buys, sells = entries[entries["signal"] == "BUY"], entries[entries["signal"] == "SELL"]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Symbols scanned", f"{len(data):,}")
        m2.metric("Setup ready", f"{len(ready):,}")
        m3.metric("Sweep found", f"{len(swept):,}")
        m4.metric("BUY entries", f"{len(buys):,}")
        m5.metric("SELL entries", f"{len(sells):,}")
        view = ready if only_ready else data
        view = view.sort_values(["stage", "symbol"], ascending=[False, True])
        st.subheader("Scanner dashboard")
        search = st.text_input("Filter symbol", placeholder="e.g. RELIANCE")
        if search: view = view[view.symbol.str.contains(search.upper(), na=False)]
        cols = ["symbol", "bias", "m1_high", "m1_low", "m2_high", "m2_low", "m2_close",
                "stage_text", "ltp", "entry", "sl", "t1", "t2", "invalidation"]
        st.dataframe(view[cols], use_container_width=True, hide_index=True,
                     column_config={
                         "symbol": st.column_config.TextColumn("Symbol"),
                         "bias": st.column_config.TextColumn("Bias"),
                         "stage_text": st.column_config.TextColumn("Stage"),
                         "ltp": st.column_config.NumberColumn("LTP", format="₹%.2f"),
                         "entry": st.column_config.NumberColumn("Entry", format="₹%.2f"),
                         "sl": st.column_config.NumberColumn("SL", format="₹%.2f"),
                         "t1": st.column_config.NumberColumn("T1", format="₹%.2f"),
                         "t2": st.column_config.NumberColumn("T2", format="₹%.2f"),
                     })
        st.download_button("⬇ Download scan results (CSV)", data=view.to_csv(index=False).encode("utf-8"),
                           file_name="crt_nse_scan.csv", mime="text/csv")
        if st.session_state.scan_errors:
            with st.expander(f"Symbols without data / errors ({len(st.session_state.scan_errors)})"):
                st.dataframe(pd.DataFrame([{"symbol": k, "reason": v} for k, v in st.session_state.scan_errors.items()]),
                             use_container_width=True, hide_index=True)
else:
    st.markdown("""
    **Signal stages**
    - **Stage 1 — Wait Sweep:** M2 creates the CRT bias relative to M1.
    - **Stage 2 — Wait CHoCH:** Price sweeps the prior rolling high/low and closes back inside.
    - **Stage 3 — BUY / SELL:** Displacement candle breaks the latest confirmed pivot (fallback: 5-day high/low).

    The scanner uses daily OHLC history, the Pine script's default ATR / pivot / sweep / entry parameters,
    and confirmed closed daily candles by default. The live NSE equity list is fetched when the app loads.
    """)
    st.caption("Press “Scan NSE stocks” to start. Test a smaller batch before a full-universe run.")

st.divider()
st.caption("Market data is supplied by Yahoo Finance and may be delayed, incomplete, or unavailable for some NSE symbols. Research use only; not investment advice.")

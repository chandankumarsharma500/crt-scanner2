from __future__ import annotations
import pandas as pd
import streamlit as st
from scanner import scan_symbol
from universe import load_nse_symbols, MARKET_WATCHLISTS, download_market_histories

st.set_page_config(page_title="CRT Multi-Market Scanner", page_icon="📈", layout="wide")
st.markdown("""
<style>
.stApp{background:radial-gradient(ellipse at 10% 0%,rgba(0,118,255,.2),transparent 38%),linear-gradient(145deg,#050d1d,#07172e 55%,#061225);color:#edf5ff}
.block-container{max-width:1550px;padding-top:2rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0b1c36,#071326);border-right:1px solid #24496f}
h1,h2,h3{color:#f4f8ff!important}.stMarkdown,p,label{color:#c7d7ee}
.hero{padding:25px 30px;margin-bottom:20px;border-radius:22px;background:linear-gradient(110deg,#0c2a52,#051930 58%,#005c53);border:1px solid #2bb4ff66}
.kicker{color:#51f0bd;font-size:.78rem;font-weight:800;letter-spacing:.18em}
.big{font-size:clamp(2rem,4vw,3.2rem);font-weight:900;color:white}.big span{color:#50edaa}
div[data-testid="stMetric"]{background:linear-gradient(145deg,#0e2b4e,#07192f);border:1px solid #3e97e64d;border-radius:16px;padding:14px}
div[data-testid="stMetricValue"]{color:#54efb0!important;font-weight:850}
.stButton>button,.stDownloadButton>button{border-radius:12px;border:1px solid #4adeaa;background:linear-gradient(100deg,#087fcb,#08b981);color:#041629;font-weight:800;min-height:2.8rem}
div[data-testid="stDataFrame"]{border:1px solid #4397e252;border-radius:14px;overflow:hidden}
</style>
<div class="hero"><div class="kicker">ONE CLICK · SEVEN MARKET PANELS</div>
<div class="big">🛡️ CRT <span>MULTI-MARKET</span> SCANNER</div>
<div>Scan · Detect · Verify &nbsp; | &nbsp; M1 CRT → M2 Sweep → M3 Entry</div></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## ⚙️ Scanner settings")
    period = st.selectbox("Historical data", ["3y","5y","2y"], index=0)
    nse_limit = st.selectbox("NSE symbols per scan", ["All NSE stocks",500,1000,2000], index=0)
    workers = st.slider("Parallel downloads",2,12,8)
    st.divider()
    st.markdown("### 🎯 CRT strategy")
    atr_len=st.number_input("ATR Length",1,100,14)
    disp=st.number_input("Displacement × ATR",0.1,10.0,1.2,0.1)
    piv_l=st.number_input("Pivot Left",1,20,3)
    piv_r=st.number_input("Pivot Right",1,20,3)
    sweep_lb=st.number_input("Sweep Lookback (daily bars)",3,60,10)
    entry_lb=st.number_input("Entry valid (daily candles)",1,10,3)
    confirmed=st.checkbox("Only confirmed / closed daily candles",value=True)
    only_ready=st.checkbox("Show only setup-ready symbols",value=True)

@st.cache_data(ttl=3600,show_spinner=False)
def get_nse_universe():
    return load_nse_symbols()

try:
    nse_symbols=get_nse_universe()["SYMBOL"].tolist()
except Exception as exc:
    nse_symbols=[]
    st.warning(f"NSE live list unavailable: {exc}. Other market panels can still scan.")

market_items={"NSE – Indian Stocks":[(s,f"{s}.NS") for s in nse_symbols]}
for market, config in MARKET_WATCHLISTS.items():
    market_items[market]=[(ticker,ticker) for ticker in config["symbols"]]

if "market_results" not in st.session_state:
    st.session_state.market_results={}
if "market_errors" not in st.session_state:
    st.session_state.market_errors={}

st.markdown("### 🌐 Seven independent market panels")
st.caption("All panels use the same CRT rules and one shared Scan All button. Market data availability depends on Yahoo Finance coverage.")
summary=st.columns(7)
for col,(market,items) in zip(summary,market_items.items()):
    col.metric(market.split("–")[0].strip(),len(items))

start=st.button("🚀 SCAN ALL MARKETS",type="primary",use_container_width=True)
if start:
    total=sum(len(v) for v in market_items.values())
    progress=st.progress(0,text="Preparing all market scans…")
    status=st.empty()
    completed=0
    all_results={}
    all_errors={}
    for market,items in market_items.items():
        if not items:
            all_results[market]=pd.DataFrame()
            continue
        # One global button triggers each market sequentially; each panel retains its own results.
        def callback(done, count, symbol, market_name=market):
            nonlocal_dummy = None
            status.caption(f"{market_name}: downloaded {done:,}/{count:,} · {symbol}")
        histories,errors=download_market_histories(items,period,workers,callback)
        rows=[]
        for symbol,history in histories.items():
            try:
                rows.append(scan_symbol(symbol,history,int(atr_len),float(disp),int(piv_l),
                    int(piv_r),int(sweep_lb),int(entry_lb),bool(confirmed)).to_dict())
            except Exception as exc:
                errors[symbol]=f"Scanner error: {exc}"
        frame=pd.DataFrame(rows)
        if not frame.empty:
            frame.insert(0,"market",market)
        all_results[market]=frame
        all_errors[market]=errors
        completed+=len(items)
        progress.progress(min(completed/max(total,1),1.0),text=f"Finished {market}")
    st.session_state.market_results=all_results
    st.session_state.market_errors=all_errors
    progress.empty();status.empty()
    st.success("All market scans finished. Open each panel below to inspect its independent results.")

results=st.session_state.market_results
if results:
    frames=[df for df in results.values() if df is not None and not df.empty]
    combined=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    if not combined.empty:
        entries=combined[combined.stage==3]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Total scanned",f"{len(combined):,}")
        c2.metric("Setup ready",f"{int((combined.stage>=1).sum()):,}")
        c3.metric("BUY signals",f"{int((entries.signal=='BUY').sum()):,}")
        c4.metric("SELL signals",f"{int((entries.signal=='SELL').sum()):,}")
        st.download_button("⬇ Download combined results CSV",combined.to_csv(index=False).encode("utf-8"),
            "crt_all_markets.csv","text/csv")
    st.markdown("### 📊 Market-wise results")
    tabs=st.tabs(list(market_items.keys()))
    display_cols=["symbol","bias","stage_text","signal","ltp","entry","sl","t1","t2","m1_high","m1_low","m2_high","m2_low"]
    for tab,market in zip(tabs,market_items):
        with tab:
            df=results.get(market,pd.DataFrame())
            st.markdown(f"#### {market}")
            if df is None or df.empty:
                st.info("No usable data returned for this panel yet.")
            else:
                view=df[df.stage>=1].copy() if only_ready else df.copy()
                view=view.sort_values(["stage","symbol"],ascending=[False,True])
                query=st.text_input("Filter this market",key=f"filter_{market}",placeholder="Search symbol")
                if query:
                    view=view[view.symbol.str.contains(query.upper(),na=False)]
                st.metric("Symbols scanned",len(df))
                st.dataframe(view[[c for c in display_cols if c in view.columns]],
                    use_container_width=True,hide_index=True,
                    column_config={"ltp":st.column_config.NumberColumn("LTP",format="%.4f"),
                    "entry":st.column_config.NumberColumn("Entry",format="%.4f"),
                    "sl":st.column_config.NumberColumn("SL",format="%.4f"),
                    "t1":st.column_config.NumberColumn("T1",format="%.4f"),
                    "t2":st.column_config.NumberColumn("T2",format="%.4f")})
                st.download_button(f"Download {market} CSV",view.to_csv(index=False).encode("utf-8"),
                    file_name=f"crt_{market.split('–')[0].strip().lower().replace('/','_').replace(' ','_')}.csv",
                    mime="text/csv",key=f"download_{market}")
            errors=st.session_state.market_errors.get(market,{})
            if errors:
                with st.expander(f"Data errors / unavailable symbols ({len(errors)})"):
                    st.dataframe(pd.DataFrame([{"symbol":k,"reason":v} for k,v in errors.items()]),
                        use_container_width=True,hide_index=True)
else:
    st.info("Press the single SCAN ALL MARKETS button to run all seven panels. Results will remain separated by market.")
    st.markdown("""
**Signal stages**
- **Stage 1 — Wait Sweep:** M2 defines bullish/bearish CRT bias relative to M1.
- **Stage 2 — Wait CHoCH:** Price sweeps a prior rolling high/low and closes back inside.
- **Stage 3 — BUY / SELL:** Displacement candle breaks the latest confirmed pivot.

**Coverage note:** NSE uses the live Series EQ list. BSE, indices, commodities, forex, crypto and US stocks use curated Yahoo Finance ticker watchlists; these are not exhaustive exchange-wide listings. Yahoo Finance data can be delayed, incomplete or unavailable. This tool is for research, not investment advice.
""")
st.divider()
st.caption("Daily OHLC data via Yahoo Finance. No orders are placed. Validate signals independently before trading.")

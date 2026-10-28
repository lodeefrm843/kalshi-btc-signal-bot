import math
from datetime import datetime, timezone
import requests
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="BTC 15m Signal Bot", page_icon="₿", layout="centered")
BASE = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com"
TIMEOUT = 8

st.title("₿ Kalshi BTC 15-Minute Signal Bot")
st.caption("Read-only research tool · No orders placed · Experimental signals, not financial advice")

with st.sidebar:
    st.header("Signal settings")
    refresh = st.selectbox("Refresh interval", [15, 30, 60], index=1, format_func=lambda x: f"{x} seconds")
    min_edge = st.slider("Minimum estimated edge vs. market", 0.01, 0.20, 0.05, 0.01)
    min_conf = st.slider("Minimum directional probability", 0.51, 0.75, 0.57, 0.01)
    st.caption("Thresholds are filters, not evidence of a profitable strategy. Validate with logged results first.")

st_autorefresh(interval=refresh * 1000, key="signal_refresh")

@st.cache_data(ttl=10)
def get_markets():
    r = requests.get(f"{BASE}/markets", params={"series_ticker":"KXBTC15M", "status":"open", "limit":100}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("markets", [])

@st.cache_data(ttl=8)
def get_candles():
    # Coinbase public BTC-USD candles; 60-second granularity. This is a spot-price proxy,
    # not Kalshi's official CF Benchmarks settlement index.
    now = int(datetime.now(timezone.utc).timestamp())
    r = requests.get(f"{COINBASE}/products/BTC-USD/candles", params={"granularity":60, "start":datetime.fromtimestamp(now-3600, timezone.utc).isoformat(), "end":datetime.fromtimestamp(now, timezone.utc).isoformat()}, headers={"User-Agent":"BTC15mSignalResearch/1.0"}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data, columns=["time","low","high","open","close","volume"])
    if not df.empty:
        df = df.sort_values("time").reset_index(drop=True)
    return df

def num(m, *keys):
    for k in keys:
        v = m.get(k)
        if v is not None and v != "":
            try: return float(v)
            except (TypeError, ValueError): pass
    return None

def ask_price(m, side):
    # Prefer a directly supplied ask. If absent, infer binary ask from the opposing bid:
    # YES ask = 1 - NO bid; NO ask = 1 - YES bid.
    dollar = num(m, f"{side}_ask_dollars")
    if dollar is not None: return dollar
    cents = num(m, f"{side}_ask")
    if cents is not None: return cents / 100
    opposite = "no" if side == "yes" else "yes"
    opp_dollar = num(m, f"{opposite}_bid_dollars")
    if opp_dollar is not None: return max(0.0, min(1.0, 1.0 - opp_dollar))
    opp_cents = num(m, f"{opposite}_bid")
    return max(0.0, min(1.0, 1.0 - opp_cents/100)) if opp_cents is not None else None

def build_signal(market, candles):
    if candles.empty or len(candles) < 8:
        raise ValueError("Not enough BTC candles yet")
    close = candles["close"].astype(float).reset_index(drop=True)
    spot = float(close.iloc[-1])
    r1 = spot / float(close.iloc[-2]) - 1
    r3 = spot / float(close.iloc[-4]) - 1
    r5 = spot / float(close.iloc[-6]) - 1
    returns = close.pct_change().dropna().tail(30)
    sigma = float(returns.std()) if len(returns) > 3 else 0.0005
    sigma = max(sigma, 0.00008)

    strike = num(market, "floor_strike", "strike_price", "floor_strike_dollars")
    close_ts = num(market, "close_ts", "expiration_ts")
    now_ts = datetime.now(timezone.utc).timestamp()
    secs_left = max(0, int(close_ts-now_ts)) if close_ts else None
    mins_left = max(0.25, (secs_left or 900)/60)

    # A transparent heuristic score combines multi-horizon momentum and distance to strike.
    # The probability is deliberately shrunk toward 50%; it is not a trained/validated model.
    momentum = (0.20*r1 + 0.35*r3 + 0.45*r5) / max(sigma*math.sqrt(5), 0.0002)
    momentum = max(-2.0, min(2.0, momentum))
    distance = ((spot/strike)-1) if strike and strike > 0 else 0.0
    distance_score = max(-1.5, min(1.5, distance / max(sigma*math.sqrt(mins_left), 0.0003)))
    score = 0.60*momentum + 0.40*distance_score
    p_up = 0.5 + 0.18*math.tanh(score/1.5)
    p_up = max(0.35, min(0.65, p_up))
    p_down = 1-p_up

    yes_ask = ask_price(market, "yes")
    no_ask = ask_price(market, "no")
    # Missing asks should remain unknown rather than inferred from a stale bid.
    if p_up >= p_down:
        side, prob, ask = "UP", p_up, yes_ask
    else:
        side, prob, ask = "DOWN", p_down, no_ask
    edge = prob-ask if ask is not None else None
    if prob < min_conf or edge is None or edge < min_edge:
        action = "NO TRADE"
    else:
        action = side
    return {"spot":spot,"r1":r1,"r3":r3,"r5":r5,"strike":strike,"secs_left":secs_left,
            "p_up":p_up,"p_down":p_down,"side":side,"prob":prob,"ask":ask,"edge":edge,"action":action,
            "yes_ask":yes_ask,"no_ask":no_ask}

try:
    markets = get_markets()
    if not markets:
        st.warning("No open KXBTC15M market was returned. Try refreshing, or check Kalshi's BTC 15-minute market page.")
        st.stop()
    # Prefer market with the latest close time among currently open markets.
    market = max(markets, key=lambda m: num(m, "close_ts") or 0)
    candles = get_candles()
    s = build_signal(market, candles)
except Exception as e:
    st.error(f"Could not load live data: {e}")
    st.info("The signal needs the Kalshi public market endpoint and Coinbase public BTC-USD candles. Retry in a few seconds if either feed is temporarily unavailable.")
    st.stop()

col1, col2 = st.columns(2)
with col1: st.metric("BTC spot reference", f"${s['spot']:,.2f}")
with col2: st.metric("Time left", f"{s['secs_left']//60:02d}:{s['secs_left']%60:02d}" if s['secs_left'] is not None else "Unknown")

st.subheader("Current signal")
action = s["action"]
if action == "UP": st.success("UP signal — heuristic only")
elif action == "DOWN": st.error("DOWN signal — heuristic only")
else: st.warning("NO TRADE — insufficient estimated edge or missing price")

c1,c2,c3 = st.columns(3)
c1.metric("Estimated UP probability", f"{s['p_up']:.1%}")
c2.metric("Estimated DOWN probability", f"{s['p_down']:.1%}")
c3.metric("Estimated edge", f"{s['edge']:+.1%}" if s['edge'] is not None else "Unavailable")

st.subheader("Market details")
st.write("**Market:**", market.get("title") or market.get("ticker", "Unknown"))
st.write("**Ticker:**", market.get("ticker", "Unknown"))
st.write("**Strike / reference:**", f"${s['strike']:,.2f}" if s['strike'] else "Not provided by API")
st.write("**UP (YES) ask:**", f"${s['yes_ask']:.2f}" if s['yes_ask'] is not None else "Unavailable")
st.write("**DOWN (NO) ask:**", f"${s['no_ask']:.2f}" if s['no_ask'] is not None else "Unavailable")
st.write("**Momentum:**", f"1m {s['r1']:+.3%} · 3m {s['r3']:+.3%} · 5m {s['r5']:+.3%}")
st.caption("BTC spot is from Coinbase and may differ from the CF Benchmarks index used for settlement. Verify the exact market rules and displayed order book on Kalshi.")

st.subheader("Suggested price discipline")
if s['prob'] is not None:
    st.write(f"Raw model probability for {s['side']}: **{s['prob']:.1%}**")
    st.write(f"Before fees, the theoretical break-even price is about **{s['prob']*100:.0f}¢**. Do not use this as an order instruction: subtract expected fees and a safety margin, and treat this heuristic as unvalidated.")

st.subheader("Risk controls")
st.markdown("""
- Signals only: this app never submits orders.
- Start with **$0 real-money risk** while evaluating signals.
- Log every signal and final settlement; evaluate calibration and performance over at least 100–200 windows before drawing conclusions.
- Avoid a signal when feeds are stale, the market/strike is missing, the spread is wide, or fewer than 60 seconds remain.
- Never increase stake to recover a loss; set a fixed maximum amount before any future manual trade.
""")
st.caption(f"Last refreshed: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} · Auto-refresh is controlled by the Streamlit app settings below.")

st.markdown("---")
st.caption("This app refreshes automatically at the interval selected in the sidebar. It intentionally does not store personal data or connect to your Kalshi account.")

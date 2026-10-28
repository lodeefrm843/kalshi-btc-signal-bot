# Kalshi BTC 15-Minute Signal Bot (read-only)

A Streamlit dashboard that reads the currently open `KXBTC15M` market from Kalshi's public REST API and BTC-USD 1-minute candles from Coinbase. It emits a heuristic UP/DOWN/NO TRADE signal. It does not place orders and does not require Kalshi credentials.

## Important limitations

- This is a research starter, not a proven predictive model or financial advice.
- The signal is a transparent, untrained heuristic, not a backtested edge. Probabilities are deliberately shrunk toward 50% and should not be interpreted as calibrated forecasts.
- Coinbase BTC spot is only a reference proxy. Kalshi's 15-minute crypto market may settle on a CF Benchmarks index and a market-specific averaging method. The exact market rules control.
- No real-money orders are placed. Keep it read-only.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## View on iPhone using Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `requirements.txt`, and this README.
2. Sign in to Streamlit Community Cloud and create an app from that repository, selecting `app.py` as the main file.
3. Open the generated app URL in Safari and optionally use Share → Add to Home Screen.
4. If you do not have a computer, use GitHub's website in Safari to create the repository and add the files, then deploy from Streamlit Community Cloud.

## Risk controls

- Start with no real-money exposure.
- Record each signal, market ticker, timestamp, estimated probability, displayed contract price, and final settlement.
- Assess calibration, Brier score, and net results after fees over at least 100–200 completed windows before considering any manual use.
- Do not treat a displayed edge as actionable without correct fee estimates and a live executable ask.
- Never paste API secrets into this app or public GitHub repository.

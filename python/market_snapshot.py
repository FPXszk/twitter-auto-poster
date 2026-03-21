from __future__ import annotations

import yfinance as yf


def fetch_market_snapshot(ticker: str) -> tuple[float, float]:
    try:
        history = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
    except Exception as error:
        raise RuntimeError(f"failed to download market data for {ticker}") from error

    if history.empty or "Close" not in history.columns:
        raise ValueError(f"no market close data returned for {ticker}")

    closes = history["Close"].dropna()
    if len(closes.index) < 2:
        raise ValueError(f"insufficient market close history for {ticker}")

    previous_close = float(closes.iloc[-2])
    current_close = float(closes.iloc[-1])
    if previous_close == 0:
        raise ValueError(f"previous market close is zero for {ticker}")

    pct_change = ((current_close - previous_close) / previous_close) * 100.0
    return current_close, pct_change

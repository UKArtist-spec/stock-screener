"""ดึงข้อมูลจาก Yahoo Finance (yfinance) + โหมด demo (ข้อมูลจำลอง ใช้ทดสอบ UI ได้โดยไม่ต้องต่อเน็ต)"""
from __future__ import annotations

import json
import os
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_UNIVERSE = (
    "MSFT AAPL GOOGL AMZN META NVDA AVGO ADBE CRM NOW INTU V MA COST NFLX ISRG "
    "LLY NVO TMO ASML TSM ANET PANW CRWD SNPS CDNS ORLY FICO SPGI MCO "
    "QQQ VGT SMH VUG SCHG MGK QQQM IWF SPY VOO"
).split()


def load_moat_tags() -> dict:
    """แท็ก Moat ที่ผู้ใช้กำหนดเอง (แก้ไฟล์ moat.json ได้)"""
    try:
        with open(os.path.join(HERE, "moat.json"), encoding="utf-8") as f:
            return {k.upper(): v for k, v in json.load(f).items() if not k.startswith("_")}
    except Exception:
        return {}


def load_sp500() -> list[str]:
    """รายชื่อ S&P 500 (Wikipedia บล็อกคำขอที่ไม่มี User-Agent จึงระบุเอง และมี CSV สำรอง)"""
    import io

    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"}
    sources = [
        ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "wiki"),
        ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", "csv"),
    ]
    last = None
    for url, kind in sources:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            tbl = pd.read_html(io.StringIO(r.text))[0] if kind == "wiki" else pd.read_csv(io.StringIO(r.text))
            syms = [str(x).strip().replace(".", "-") for x in tbl["Symbol"].tolist()]
            if len(syms) > 400:
                return syms
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"โหลดรายชื่อไม่สำเร็จ: {last}")


# ชุด ETF ตามแผนการลงทุน (จากภาพ ETF HACK)
ETF_SETS = {
    "1 Balanced (พอร์ตสมดุล)": ["VOO", "VTI", "VT"],
    "2 Tech (เทคโนโลยี)": ["QQQM", "SCHG", "XLK"],
    "3 Sector (รายอุตสาหกรรม)": ["SMH", "XLV", "XLE"],
    "4 Dividend (ปันผล)": ["SCHD", "VYM", "VIG"],
    "5 Global (ทั่วโลก)": ["VEA", "IEMG", "VXUS"],
    "6 Commodity (สินค้าโภคภัณฑ์)": ["GLDM", "SIVR", "USO"],
    "7 Small Cap (หุ้นเล็ก)": ["IWM", "IJR", "AVUV"],
    "8 Real Estate (อสังหาฯ)": ["XLRE", "ITB", "SCHH"],
    "9 Bond (ตราสารหนี้)": ["SGOV", "BND", "TLT"],
    "ETF เด่น 5 ตัว": ["VOO", "QQQM", "GLDM", "SMH", "SGOV"],
}


def load_etf_set(name: str, include_holdings: bool = True) -> list[str]:
    """ETF ในชุดนั้น + (ถ้าเลือก) หุ้น top holdings ข้างใน (Yahoo ให้ประมาณ 10 ตัว/กองทุน)"""
    import re

    import yfinance as yf

    etfs = list(ETF_SETS[name])
    out = list(etfs)
    if include_holdings:
        for e in etfs:
            try:
                for sym in yf.Ticker(e).funds_data.top_holdings.index:
                    sym = str(sym).strip().upper()
                    if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", sym):
                        out.append(sym)
            except Exception:  # noqa: BLE001  (กองทุนทอง/พันธบัตรไม่มีหุ้นข้างใน)
                pass
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ helpers
def _row(df: pd.DataFrame | None, *names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce").dropna()
            if not s.empty:
                return s.sort_index()
    return None


def _fetch_real(ticker: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    out = {"ticker": ticker, "info": info, "type": info.get("quoteType", "EQUITY"),
           "name": info.get("shortName") or info.get("longName") or ticker, "fin": {}, "holdings": None}
    if out["type"] == "ETF":
        try:
            h = t.funds_data.top_holdings
            out["holdings"] = {sym: float(w) for sym, w in h["Holding Percent"].items()}
        except Exception:
            out["holdings"] = {}
        return out
    inc, bal, cf = t.financials, t.balance_sheet, t.cashflow
    fin = {
        "revenue": _row(inc, "Total Revenue", "Operating Revenue"),
        "eps": _row(inc, "Diluted EPS", "Basic EPS"),
        "ebit": _row(inc, "EBIT", "Operating Income"),
        "gross_profit": _row(inc, "Gross Profit"),
        "tax_provision": _row(inc, "Tax Provision"),
        "pretax_income": _row(inc, "Pretax Income"),
        "interest_expense": _row(inc, "Interest Expense", "Interest Expense Non Operating"),
        "total_debt": _row(bal, "Total Debt"),
        "cash": _row(bal, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
        "invested_capital": _row(bal, "Invested Capital"),
        "fcf": _row(cf, "Free Cash Flow"),
    }
    if fin["invested_capital"] is None:
        eq = _row(bal, "Stockholders Equity", "Total Equity Gross Minority Interest")
        if eq is not None and fin["total_debt"] is not None and fin["cash"] is not None:
            fin["invested_capital"] = eq + fin["total_debt"] - fin["cash"]
    if fin["fcf"] is None:
        ocf, capex = _row(cf, "Operating Cash Flow"), _row(cf, "Capital Expenditure")
        if ocf is not None and capex is not None:
            fin["fcf"] = ocf + capex  # capex ติดลบใน Yahoo
    out["fin"] = fin
    return out


# ------------------------------------------------------------------ demo
def _fetch_demo(ticker: str) -> dict:
    rng = np.random.default_rng(zlib.crc32(ticker.encode()))
    yrs = pd.date_range("2022-12-31", periods=4, freq="YE")

    def series(start, g, noise=0.03):
        v = [start]
        for _ in range(3):
            v.append(v[-1] * (1 + g + rng.normal(0, noise)))
        return pd.Series(v, index=yrs)

    if ticker in {"QQQ", "VGT", "SMH", "VUG", "SCHG", "MGK", "QQQM", "IWF", "SPY", "VOO"}:
        picks = ["MSFT", "AAPL", "NVDA", "AMZN", "GOOGL"]
        w = rng.dirichlet(np.ones(5)) * 0.4
        return {"ticker": ticker, "info": {"quoteType": "ETF"}, "type": "ETF", "name": f"{ticker} (demo ETF)",
                "fin": {}, "holdings": dict(zip(picks, map(float, w)))}
    g = rng.uniform(0.0, 0.25)
    rev = series(rng.uniform(5e9, 2e11), g)
    margin = rng.uniform(0.05, 0.4)
    ebit = rev * margin * np.linspace(0.9, 1.05, 4)
    debt = pd.Series(rev.iloc[-1] * rng.uniform(0, 0.6), index=yrs) * np.ones(4)
    cash = pd.Series(rev.iloc[-1] * rng.uniform(0.05, 0.3), index=yrs) * np.ones(4)
    fin = {
        "revenue": rev, "eps": series(rng.uniform(1, 10), g * rng.uniform(0.6, 1.6), 0.05),
        "ebit": ebit, "gross_profit": rev * rng.uniform(0.3, 0.8), "tax_provision": ebit * 0.18,
        "pretax_income": ebit, "interest_expense": debt * 0.04, "total_debt": debt, "cash": cash,
        "invested_capital": rev * rng.uniform(0.25, 0.8), "fcf": ebit * rng.uniform(0.6, 0.9) * np.linspace(0.85, 1.1, 4),
    }
    info = {"quoteType": "EQUITY", "forwardPE": float(rng.uniform(15, 55)),
            "trailingPE": float(rng.uniform(15, 60)), "marketCap": float(rev.iloc[-1] * rng.uniform(4, 14))}
    return {"ticker": ticker, "info": info, "type": "EQUITY", "name": f"{ticker} (demo)", "fin": fin, "holdings": None}


def fetch_one(ticker: str, demo: bool = False) -> dict:
    try:
        return _fetch_demo(ticker) if demo else _fetch_real(ticker)
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "error": str(e), "fin": {}, "info": {}, "type": "ERR", "name": ticker, "holdings": None}


def fetch_many(tickers: list[str], demo: bool = False, workers: int = 8) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return {d["ticker"]: d for d in ex.map(lambda t: fetch_one(t, demo), tickers)}


# ------------------------------------------------------------------ ราคา
def fetch_quotes(tickers: list[str], demo: bool = False) -> pd.DataFrame:
    """ราคาล่าสุด + % เปลี่ยนแปลงวันนี้ / 1 เดือน / ห่างจากจุดสูงสุด 52 สัปดาห์ (Yahoo ฟรีดีเลย์ ~15 นาที)"""
    cols = ["Price", "Today %", "1M %", "From 52w high %", "1Y trend"]
    if demo:
        rows = {}
        for t in tickers:
            r = np.random.default_rng(zlib.crc32(t.encode()) + int(pd.Timestamp.now().timestamp() // 30))
            rows[t] = [float(r.uniform(50, 600)), float(r.normal(0, 1.2)), float(r.normal(1, 5)), float(-abs(r.normal(8, 8))),
                        list(np.cumsum(r.normal(0.2, 2, 60)) + 100)]
        return pd.DataFrame.from_dict(rows, orient="index", columns=cols)
    import yfinance as yf

    px = yf.download(tickers, period="1y", interval="1d", auto_adjust=True, progress=False, threads=True)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0])
    rows = {}
    for t in px.columns:
        s = px[t].dropna()
        if len(s) < 25:
            continue
        rows[t] = [float(s.iloc[-1]), (s.iloc[-1] / s.iloc[-2] - 1) * 100, (s.iloc[-1] / s.iloc[-22] - 1) * 100,
                   (s.iloc[-1] / s.max() - 1) * 100, s.iloc[-260:].iloc[::5].round(2).tolist()]
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)

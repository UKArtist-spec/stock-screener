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


def _get_html(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"}, timeout=25)
    r.raise_for_status()
    return r.text


def _sp500_df() -> pd.DataFrame:
    """ตาราง S&P 500 (Symbol, GICS Sector, GICS Sub-Industry) จาก Wikipedia และมี CSV สำรอง"""
    import io

    last = None
    for url, kind in [
        ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "wiki"),
        ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", "csv"),
    ]:
        try:
            txt = _get_html(url)
            df = pd.read_html(io.StringIO(txt))[0] if kind == "wiki" else pd.read_csv(io.StringIO(txt))
            if len(df) > 400 and "Symbol" in df:
                df["Symbol"] = df["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False)
                return df
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"โหลดรายชื่อไม่สำเร็จ: {last}")


def load_sp500() -> list[str]:
    return _sp500_df()["Symbol"].tolist()


# รายชื่อสำรองเมื่อดึงจากเน็ตไม่ได้ (โดยประมาณ ณ ปี 2025 สมาชิกอาจเปลี่ยนตามรอบทบทวนของ Nasdaq)
NASDAQ100_FALLBACK = (
    "AAPL MSFT NVDA AMZN META GOOGL GOOG AVGO TSLA COST NFLX ASML TMUS CSCO PEP LIN ADBE AMD TXN QCOM INTU AMGN ISRG "
    "BKNG HON AMAT CMCSA PDD VRTX ADP SBUX PANW GILD MU ADI LRCX MELI INTC KLAC REGN CDNS SNPS CRWD MAR PYPL CEG CTAS "
    "MDLZ ORLY CSX ABNB DASH WDAY ADSK FTNT ROP NXPI MNST PCAR CPRT AEP KDP FANG PAYX ODFL ROST CHTR FAST EXC MRVL BKR "
    "EA XEL TTWO CSGP GEHC DDOG IDXX VRSK CCEP ON LULU TEAM ZS DXCM CDW BIIB GFS MDB TTD ARM APP PLTR AXON SHOP CTSH KHC"
).split()


def _nasdaq100() -> tuple[list[str], str]:
    """คืน (รายชื่อ, แหล่งที่มา) ลองหลายแหล่งตามลำดับ"""
    import io

    errs = []
    try:  # 1) API ทางการของ Nasdaq
        import requests

        r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=20)
        r.raise_for_status()
        rows = r.json()["data"]["data"]["rows"]
        syms = [str(x["symbol"]).strip().replace(".", "-") for x in rows]
        if len(syms) >= 90:
            return syms, "Nasdaq.com"
    except Exception as e:  # noqa: BLE001
        errs.append(f"nasdaq.com: {e}")
    try:  # 2) Wikipedia (หาตารางที่มีคอลัมน์ Ticker/Symbol ประมาณ 100 แถว)
        for t in pd.read_html(io.StringIO(_get_html("https://en.wikipedia.org/wiki/Nasdaq-100"))):
            for col in t.columns:
                if str(col).strip() in ("Ticker", "Symbol") and 90 <= len(t) <= 115:
                    return [str(x).strip().replace(".", "-") for x in t[col].tolist()], "Wikipedia"
    except Exception as e:  # noqa: BLE001
        errs.append(f"wikipedia: {e}")
    return list(NASDAQ100_FALLBACK), "รายชื่อสำรองในแอพ (ประมาณ)"


def _etf_holdings(etf: str) -> list[str]:
    """หุ้น top holdings ของ ETF (Yahoo ให้ ~10 ตัว) เก็บเฉพาะ ticker สหรัฐ/ADR"""
    import re

    try:
        import yfinance as yf

        idx = yf.Ticker(etf).funds_data.top_holdings.index
    except Exception:  # noqa: BLE001
        return []
    return [str(x).strip().upper() for x in idx if re.fullmatch(r"[A-Za-z]{1,5}(-[A-Za-z])?", str(x).strip())]


# ปุ่มกลุ่มหุ้น: ชื่อปุ่ม -> (ETF อ้างอิง, วิธีหารายชื่อ)
GROUPS = {
    "Nasdaq 100": ("QQQM", "nasdaq100"),
    "Semiconductor": ("SMH", ("sub", "Semiconductor")),
    "Health Care": ("XLV", ("sector", "Health Care")),
    "Energy": ("XLE", ("sector", "Energy")),
}


def load_group(name: str) -> tuple[list[str], str]:
    """คืน (รายชื่อ ticker, แหล่งข้อมูล)"""
    etf, how = GROUPS[name]
    out, src = [etf], "S&P 500 (Wikipedia)"
    if how == "nasdaq100":
        lst, src = _nasdaq100()
        out += lst
    else:
        kind, key = how
        df = _sp500_df()
        col = "GICS Sector" if kind == "sector" else "GICS Sub-Industry"
        out += df[df[col].astype(str).str.contains(key, case=False)]["Symbol"].tolist()
        out += _etf_holdings(etf)  # เพิ่มหุ้นนอก S&P 500 ที่กองทุนถือ เช่น TSM, ASML
    return list(dict.fromkeys(out)), src


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
           "name": info.get("shortName") or info.get("longName") or ticker, "fin": {}, "holdings": None,
           "next_earnings": None}
    try:  # วันประกาศงบครั้งถัดไป
        cal = t.calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if ed:
            out["next_earnings"] = str(list(ed)[0])
    except Exception:  # noqa: BLE001
        pass
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
        "sbc": _row(cf, "Stock Based Compensation"),
        "net_income": _row(inc, "Net Income", "Net Income Common Stockholders"),
        "shares": _row(inc, "Diluted Average Shares", "Basic Average Shares"),
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
                "fin": {}, "holdings": dict(zip(picks, map(float, w))), "next_earnings": None}
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
        "sbc": ebit * rng.uniform(0.02, 0.3), "net_income": ebit * 0.8,
        "shares": series(rng.uniform(5e8, 5e9), rng.uniform(-0.02, 0.03), 0.005),
    }
    sectors = ["Technology", "Healthcare", "Financial Services", "Consumer Cyclical", "Energy", "Industrials"]
    info = {"quoteType": "EQUITY", "sector": sectors[int(rng.integers(0, len(sectors)))], "forwardPE": float(rng.uniform(15, 55)),
            "trailingPE": float(rng.uniform(15, 60)), "marketCap": float(rev.iloc[-1] * rng.uniform(4, 14))}
    return {"ticker": ticker, "info": info, "type": "EQUITY", "name": f"{ticker} (demo)", "fin": fin, "holdings": None,
            "next_earnings": (pd.Timestamp.now() + pd.Timedelta(days=int(rng.integers(2, 80)))).date().isoformat()}


def fetch_one(ticker: str, demo: bool = False) -> dict:
    try:
        return _fetch_demo(ticker) if demo else _fetch_real(ticker)
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "error": str(e), "fin": {}, "info": {}, "type": "ERR", "name": ticker, "holdings": None}


def fetch_many(tickers: list[str], demo: bool = False, workers: int = 8) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return {d["ticker"]: d for d in ex.map(lambda t: fetch_one(t, demo), tickers)}


# ------------------------------------------------------------------ ราคา
def _vs_ma200(s: pd.Series):
    return float((s.iloc[-1] / s.rolling(200).mean().iloc[-1] - 1) * 100) if len(s) >= 200 else float("nan")


def _rsi(s: pd.Series, n: int = 14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])) if dn.iloc[-1] else 100.0


def fetch_quotes(tickers: list[str], demo: bool = False) -> pd.DataFrame:
    """ราคาล่าสุด + % เปลี่ยนแปลงวันนี้ / 1 เดือน / ห่างจากจุดสูงสุด 52 สัปดาห์ (Yahoo ฟรีดีเลย์ ~15 นาที)"""
    cols = ["Price", "Today %", "1M %", "From 52w high %", "1Y trend", "vs MA200 %", "RSI"]
    if demo:
        rows = {}
        for t in tickers:
            r = np.random.default_rng(zlib.crc32(t.encode()) + int(pd.Timestamp.now().timestamp() // 30))
            rows[t] = [float(r.uniform(50, 600)), float(r.normal(0, 1.2)), float(r.normal(1, 5)), float(-abs(r.normal(8, 8))),
                        list(np.cumsum(r.normal(0.2, 2, 60)) + 100), float(r.normal(4, 10)), float(r.uniform(25, 75))]
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
                   (s.iloc[-1] / s.max() - 1) * 100, s.iloc[-260:].iloc[::5].round(2).tolist(), _vs_ma200(s), _rsi(s)]
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)

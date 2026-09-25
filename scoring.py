"""ตรรกะให้คะแนนหุ้นตามเกณฑ์ 8 ข้อ (ล้วนเป็นฟังก์ชันล้วน ทดสอบได้โดยไม่ต้องต่อเน็ต)

อินพุตคือ dict ของ pandas.Series (เรียงจากเก่า -> ใหม่, รายปี) + dict info
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CRITERIA = ["Revenue Growth", "EPS Growth", "ROIC", "Margin", "FCF", "Balance Sheet", "Moat", "Valuation"]

DEFAULT_WEIGHTS = {
    "Revenue Growth": 12, "EPS Growth": 12, "ROIC": 15, "Margin": 10,
    "FCF": 13, "Balance Sheet": 10, "Moat": 13, "Valuation": 15,
}


def interp(x, xs, ys):
    """แปลงค่าจริงเป็นคะแนน 0-100 แบบเส้นตรงเป็นช่วง ๆ (ค่านอกช่วงถูกตัดที่ขอบ)"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(np.interp(x, xs, ys))


def cagr(s: pd.Series | None):
    """อัตราเติบโตเฉลี่ยต่อปี (%) ต้องมีค่าบวกทั้งต้นและปลาย"""
    if s is None:
        return None
    s = s.dropna()
    if len(s) < 3:
        return None
    first, last, n = float(s.iloc[0]), float(s.iloc[-1]), len(s) - 1
    if first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1 / n) - 1) * 100


def _safe_ratio(a: pd.Series | None, b: pd.Series | None):
    if a is None or b is None:
        return None
    df = pd.concat([a, b], axis=1).dropna()
    df = df[df.iloc[:, 1] != 0]
    if df.empty:
        return None
    return df.iloc[:, 0] / df.iloc[:, 1]


def compute_roic(fin: dict) -> pd.Series | None:
    """ROIC = EBIT*(1-อัตราภาษี) / เงินลงทุน (หนี้ + ส่วนผู้ถือหุ้น - เงินสด)"""
    ebit, ic = fin.get("ebit"), fin.get("invested_capital")
    if ebit is None or ic is None:
        return None
    tax_rate = 0.21
    tp, pt = fin.get("tax_provision"), fin.get("pretax_income")
    if tp is not None and pt is not None:
        r = _safe_ratio(tp, pt)
        if r is not None:
            tax_rate = r.clip(0, 0.35)
    nopat = ebit * (1 - tax_rate)
    out = _safe_ratio(nopat, ic)
    return None if out is None else out * 100


# ---------------------------------------------------------------- 8 เกณฑ์
def score_revenue(fin):
    g = cagr(fin.get("revenue"))
    return interp(g, [0, 5, 10, 15], [0, 30, 70, 100]), g


def score_eps(fin):
    eps = fin.get("eps")
    g = cagr(eps)
    if g is None and eps is not None and len(eps.dropna()) >= 3:
        return 0.0, None  # EPS ติดลบ/ขาดทุน
    return interp(g, [0, 6, 12, 18], [0, 30, 70, 100]), g


def score_roic(fin):
    r = compute_roic(fin)
    if r is None or r.dropna().empty:
        return None, None
    r = r.dropna()
    avg = float(r.mean())
    base = interp(avg, [0, 8, 15, 25], [0, 30, 70, 100])
    penalty = min(25.0, float(r.std(ddof=0)) * 1.2)  # ไม่สม่ำเสมอ -> หักคะแนน
    if float(r.min()) < 8:
        penalty += 8
    return max(0.0, base - penalty), avg


def score_margin(fin):
    om = _safe_ratio(fin.get("ebit"), fin.get("revenue"))
    if om is None or om.dropna().empty:
        return None, None
    om = om.dropna() * 100
    level = interp(float(om.iloc[-1]), [0, 10, 20, 30], [0, 40, 75, 100])
    trend = interp(float(om.iloc[-1] - om.iloc[0]), [-5, 0, 3, 8], [0, 50, 75, 100])
    return 0.6 * level + 0.4 * trend, float(om.iloc[-1])


def score_fcf(fin):
    f = fin.get("fcf")
    if f is None or f.dropna().empty:
        return None, None
    f = f.dropna()
    if float(f.iloc[-1]) <= 0:
        return 10.0, None
    g = cagr(f)
    gscore = interp(g, [-5, 0, 8, 15], [0, 30, 70, 100]) if g is not None else 20.0
    yoy = f.pct_change().dropna()
    frac = float((yoy > 0).mean()) if len(yoy) else 0.5
    return 0.6 * gscore + 0.4 * 100 * frac, g


def score_balance(fin):
    debt, cash, f, ebit, intexp = (fin.get(k) for k in ("total_debt", "cash", "fcf", "ebit", "interest_expense"))
    if debt is None or cash is None:
        return None, None
    nd = float(debt.dropna().iloc[-1]) - float(cash.dropna().iloc[-1])
    fcf_last = float(f.dropna().iloc[-1]) if f is not None and not f.dropna().empty else None
    if nd <= 0:
        lev = 100.0
        years = 0.0
    elif fcf_last is None or fcf_last <= 0:
        lev, years = 0.0, None
    else:
        years = nd / fcf_last
        lev = interp(years, [0, 2, 4, 6], [100, 80, 40, 0])
    cov = None
    if ebit is not None and intexp is not None and not intexp.dropna().empty:
        ie = abs(float(intexp.dropna().iloc[-1]))
        if ie > 0:
            cov = interp(float(ebit.dropna().iloc[-1]) / ie, [1, 3, 8], [0, 50, 100])
        else:
            cov = 100.0
    score = lev if cov is None else 0.6 * lev + 0.4 * cov
    return score, years  # years = จำนวนปี FCF ที่ต้องใช้ล้างหนี้สุทธิ


def score_moat(fin, manual_tags: list[str] | None):
    """Moat วัดจากตัวเลขไม่ได้ตรง ๆ: ใช้ proxy (Gross margin สูง/นิ่ง + ROIC สูง) ผสมกับแท็กที่ผู้ใช้ระบุเอง"""
    gm = _safe_ratio(fin.get("gross_profit"), fin.get("revenue"))
    proxy_parts = []
    if gm is not None and not gm.dropna().empty:
        gm = gm.dropna() * 100
        proxy_parts.append(interp(float(gm.mean()), [20, 40, 60], [0, 50, 100]))
        proxy_parts.append(interp(float(gm.std(ddof=0)), [0, 2, 6], [100, 70, 20]))
    roic = compute_roic(fin)
    if roic is not None and not roic.dropna().empty:
        proxy_parts.append(interp(float(roic.mean()), [8, 15, 25], [0, 50, 100]))
    proxy = float(np.mean(proxy_parts)) if proxy_parts else None
    if manual_tags:
        manual = min(100.0, 30.0 * len(manual_tags) + 10)
        return (manual if proxy is None else 0.5 * manual + 0.5 * proxy), ", ".join(manual_tags)
    return proxy, "proxy"


def score_valuation(fin, info, eps_g, rev_g):
    pe = info.get("forwardPE") or info.get("trailingPE")
    growth = eps_g if eps_g is not None else rev_g
    peg = None
    if pe and pe > 0 and growth and growth > 0:
        peg = pe / min(growth, 40)
    peg_s = interp(peg, [0.5, 1, 1.5, 2.5, 3.5], [100, 85, 65, 30, 0]) if peg is not None else None
    if pe and pe > 0 and peg is None:
        peg_s = 10.0  # มี P/E แต่ไม่โต -> ไม่มีเหตุผลจ่ายแพง
    f, mc = fin.get("fcf"), info.get("marketCap")
    fy = None
    if f is not None and not f.dropna().empty and mc:
        fy = float(f.dropna().iloc[-1]) / mc * 100
    fy_s = interp(fy, [0, 2, 4, 6], [0, 40, 75, 100]) if fy is not None else None
    parts = [(peg_s, 0.6), (fy_s, 0.4)]
    parts = [(s, w) for s, w in parts if s is not None]
    if not parts:
        return None, None
    tw = sum(w for _, w in parts)
    return sum(s * w for s, w in parts) / tw, peg


# ---------------------------------------------------------------- รวมคะแนน
def score_stock(fin: dict, info: dict, manual_tags: list[str] | None = None) -> dict:
    rev_s, rev_g = score_revenue(fin)
    eps_s, eps_g = score_eps(fin)
    roic_s, roic_avg = score_roic(fin)
    mar_s, mar_v = score_margin(fin)
    fcf_s, fcf_g = score_fcf(fin)
    bs_s, years = score_balance(fin)
    moat_s, moat_note = score_moat(fin, manual_tags)
    val_s, peg = score_valuation(fin, info, eps_g, rev_g)
    return {
        "scores": {"Revenue Growth": rev_s, "EPS Growth": eps_s, "ROIC": roic_s, "Margin": mar_s,
                   "FCF": fcf_s, "Balance Sheet": bs_s, "Moat": moat_s, "Valuation": val_s},
        "metrics": {"Revenue CAGR %": rev_g, "EPS CAGR %": eps_g, "ROIC avg %": roic_avg,
                    "Op margin %": mar_v, "FCF CAGR %": fcf_g, "ปีที่ FCF ล้างหนี้สุทธิ": years,
                    "Moat": moat_note, "PEG": peg,
                    "Forward P/E": info.get("forwardPE"), "Trailing P/E": info.get("trailingPE")},
    }


def total_score(scores: dict, weights: dict) -> float | None:
    """คะแนนรวม 0-100 (เกณฑ์ที่ไม่มีข้อมูลจะถูกตัดออกและปรับน้ำหนักใหม่)"""
    pairs = [(scores[k], weights.get(k, 0)) for k in CRITERIA if scores.get(k) is not None and weights.get(k, 0) > 0]
    tw = sum(w for _, w in pairs)
    if tw == 0:
        return None
    return sum(s * w for s, w in pairs) / tw


def rating(total: float | None, val_score: float | None) -> str:
    if total is None:
        return "ข้อมูลไม่พอ"
    if total >= 70 and (val_score or 0) >= 50:
        return "น่าซื้อ"
    if total >= 70:
        return "คุณภาพดี แต่ราคาตึง"
    if total >= 55:
        return "น่าติดตาม"
    return "ไม่ผ่านเกณฑ์"

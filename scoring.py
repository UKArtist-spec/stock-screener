"""ตรรกะให้คะแนนหุ้นตามเกณฑ์ 8 ข้อ (ล้วนเป็นฟังก์ชันล้วน ทดสอบได้โดยไม่ต้องต่อเน็ต)

อินพุตคือ dict ของ pandas.Series (เรียงจากเก่า -> ใหม่, รายปี) + dict info
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CRITERIA = ["Revenue Growth", "EPS Growth", "ROIC", "Margin", "FCF", "Balance Sheet", "Moat", "Valuation"]

DEFAULT_WEIGHTS = {
    "Revenue Growth": 12, "EPS Growth": 12, "ROIC": 15, "Margin": 10,
    "FCF": 15, "Balance Sheet": 8, "Moat": 10, "Valuation": 18,
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
    return interp(g, [0, 8, 15, 22], [0, 30, 70, 100]), g


def score_eps(fin):
    eps = fin.get("eps")
    g = cagr(eps)
    if g is None and eps is not None and len(eps.dropna()) >= 3:
        return 0.0, None  # EPS ติดลบ/ขาดทุน
    return interp(g, [0, 10, 18, 28], [0, 30, 70, 100]), g


def score_roic(fin):
    r = compute_roic(fin)
    if r is None or r.dropna().empty:
        return None, None
    r = r.dropna()
    avg = float(r.mean())
    base = interp(avg, [0, 10, 20, 30], [0, 30, 70, 100])
    penalty = min(25.0, float(r.std(ddof=0)) * 1.2)  # ไม่สม่ำเสมอ -> หักคะแนน
    if float(r.min()) < 8:
        penalty += 8
    return max(0.0, base - penalty), avg


def score_margin(fin):
    om = _safe_ratio(fin.get("ebit"), fin.get("revenue"))
    if om is None or om.dropna().empty:
        return None, None
    om = om.dropna() * 100
    level = interp(float(om.iloc[-1]), [0, 15, 25, 40], [0, 40, 75, 100])
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
    gscore = interp(g, [-5, 0, 10, 20], [0, 30, 70, 100]) if g is not None else 20.0
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
        lev = interp(years, [0, 1.5, 3, 5], [100, 80, 40, 0])
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
        manual = min(95.0, 25.0 * len(manual_tags) + 10)
        return (manual if proxy is None else 0.5 * manual + 0.5 * proxy), ", ".join(manual_tags)
    return proxy, "proxy"


def score_valuation(fin, info, eps_g, rev_g):
    pe = info.get("forwardPE") or info.get("trailingPE")
    gs = [g for g in (eps_g, rev_g) if g is not None and g > 0]
    growth = sum(gs) / len(gs) if gs else None  # เฉลี่ยโต EPS กับรายได้ กันหุ้นที่โตพุ่งปีเดียวดูถูกเกินจริง
    peg = None
    if pe and pe > 0 and growth:
        peg = pe / min(growth, 30)
    peg_s = interp(peg, [0.8, 1.2, 2, 3], [100, 75, 35, 0]) if peg is not None else None
    if pe and pe > 0 and peg is None:
        peg_s = 10.0  # มี P/E แต่ไม่โต -> ไม่มีเหตุผลจ่ายแพง
    f, mc = fin.get("fcf"), info.get("marketCap")
    fy = None
    if f is not None and not f.dropna().empty and mc:
        fy = float(f.dropna().iloc[-1]) / mc * 100
    fy_s = interp(fy, [0, 2, 4, 7], [0, 35, 70, 100]) if fy is not None else None
    parts = [(peg_s, 0.4), (fy_s, 0.6)]
    parts = [(s, w) for s, w in parts if s is not None]
    if not parts:
        return None, None
    tw = sum(w for _, w in parts)
    return sum(s * w for s, w in parts) / tw, peg


# ---------------------------------------------------------------- คุณภาพของ FCF / การเจือจางหุ้น
def fcf_quality(fin):
    """(คะแนนที่ถูกหัก, SBC/FCF, FCF/กำไรสุทธิ) หักเมื่อ FCF พึ่ง SBC มาก หรือแปลงเป็นกำไรจริงได้ต่ำ"""
    f, sbc, ni = fin.get("fcf"), fin.get("sbc"), fin.get("net_income")
    if f is None or f.dropna().empty or float(f.dropna().iloc[-1]) <= 0:
        return 0.0, None, None
    fl = float(f.dropna().iloc[-1])
    pen, ratio, conv = 0.0, None, None
    if sbc is not None and not sbc.dropna().empty:
        ratio = abs(float(sbc.dropna().iloc[-1])) / fl
        if ratio > 0.15:
            pen += min(20.0, (ratio - 0.15) * 50)
    if ni is not None and not ni.dropna().empty and float(ni.dropna().iloc[-1]) > 0:
        conv = fl / float(ni.dropna().iloc[-1])
        if conv < 0.7:
            pen += min(10.0, (0.7 - conv) * 25)
    return min(25.0, pen), ratio, conv


def share_change(fin):
    """อัตราเปลี่ยนจำนวนหุ้นต่อปี (%) บวก = เจือจาง ลบ = ซื้อหุ้นคืน"""
    sh = fin.get("shares")
    if sh is None:
        return None
    sh = sh.dropna()
    if len(sh) < 3 or float(sh.iloc[0]) <= 0 or float(sh.iloc[-1]) <= 0:
        return None
    return ((float(sh.iloc[-1]) / float(sh.iloc[0])) ** (1 / (len(sh) - 1)) - 1) * 100


# ---------------------------------------------------------------- รวมคะแนน
def score_stock(fin: dict, info: dict, manual_tags: list[str] | None = None) -> dict:
    financial = info.get("sector") == "Financial Services"  # ธนาคาร/ประกัน: ROIC, FCF, หนี้ ใช้วัดไม่ได้
    if financial:
        fin = {**fin, "fcf": None}
    rev_s, rev_g = score_revenue(fin)
    eps_s, eps_g = score_eps(fin)
    dil = share_change(fin)
    if eps_s is not None and dil is not None and eps_s > 0:
        if dil > 1:
            eps_s = max(0.0, eps_s - min(15.0, (dil - 1) * 5))
        elif dil < 0:
            eps_s = min(100.0, eps_s + min(5.0, -dil * 2))
    roic_s, roic_avg = score_roic(fin)
    mar_s, mar_v = score_margin(fin)
    fcf_s, fcf_g = score_fcf(fin)
    pen, sbc_ratio, conv = fcf_quality(fin)
    if fcf_s is not None:
        fcf_s = max(0.0, fcf_s - pen)
    bs_s, years = score_balance(fin)
    moat_s, moat_note = score_moat(fin, manual_tags)
    val_s, peg = score_valuation(fin, info, eps_g, rev_g)
    if financial:
        roic_s = mar_s = fcf_s = bs_s = None
    pct = lambda x: None if x is None else x * 100  # noqa: E731
    return {
        "scores": {"Revenue Growth": rev_s, "EPS Growth": eps_s, "ROIC": roic_s, "Margin": mar_s,
                   "FCF": fcf_s, "Balance Sheet": bs_s, "Moat": moat_s, "Valuation": val_s},
        "metrics": {"Revenue CAGR %": rev_g, "EPS CAGR %": eps_g, "ROIC avg %": roic_avg,
                    "Op margin %": mar_v, "FCF CAGR %": fcf_g, "ปีที่ FCF ล้างหนี้สุทธิ": years,
                    "จำนวนหุ้นเปลี่ยน %/ปี": dil, "SBC / FCF %": pct(sbc_ratio), "FCF / กำไรสุทธิ %": pct(conv),
                    "Moat": moat_note, "PEG": peg,
                    "Forward P/E": info.get("forwardPE"), "Trailing P/E": info.get("trailingPE"),
                    "หมายเหตุ": "กลุ่มการเงิน: ตัด ROIC, Margin, FCF, Balance Sheet ออกจากคะแนน" if financial else None},
    }


def total_score(scores: dict, weights: dict) -> float | None:
    """คะแนนรวม 0-100 (เกณฑ์ที่ไม่มีข้อมูลจะถูกตัดออกและปรับน้ำหนักใหม่)"""
    pairs = [(scores[k], weights.get(k, 0)) for k in CRITERIA if scores.get(k) is not None and weights.get(k, 0) > 0]
    tw = sum(w for _, w in pairs)
    if tw == 0:
        return None
    return sum(s * w for s, w in pairs) / tw


TOP = "ผ่านเกณฑ์เด่น"
QUALITY_PRICEY = "คุณภาพดี แต่ราคาตึง"


def rating(total: float | None, val_score: float | None) -> str:
    if total is None:
        return "ข้อมูลไม่พอ"
    if total >= 75 and (val_score or 0) >= 60:
        return TOP
    if total >= 75:
        return QUALITY_PRICEY
    if total >= 60:
        return "น่าติดตาม"
    return "ไม่ผ่านเกณฑ์"


ZONE = "ย่อตัวเข้าโซน"


def timing(from_high, vs_ma200, rsi) -> str:
    """จังหวะราคา (แยกจากคะแนนคุณภาพ): ดูระยะย่อจากจุดสูงสุด 52 สัปดาห์, แนวโน้มเทียบ MA200, RSI"""
    if from_high is None or pd.isna(from_high):
        return "-"
    if vs_ma200 is not None and not pd.isna(vs_ma200) and vs_ma200 < 0:
        return "ต่ำกว่า MA200 (ระวัง)"
    if from_high >= -8:
        return "ใกล้จุดสูงสุด"
    if from_high >= -25:
        return ZONE + (" (RSI ต่ำ)" if rsi is not None and not pd.isna(rsi) and rsi < 40 else "")
    return "ย่อลึก ตรวจสอบสาเหตุ"


def highlights(scores: dict, hi: float = 85, lo: float = 45) -> str:
    """สรุปสั้น ๆ: เกณฑ์ที่เด่น / เกณฑ์ที่อ่อน"""
    good = [k for k, v in sorted(scores.items(), key=lambda x: -(x[1] or 0)) if v is not None and v >= hi][:3]
    bad = [k for k, v in sorted(scores.items(), key=lambda x: (x[1] if x[1] is not None else 999)) if v is not None and v < lo][:2]
    parts = []
    if good:
        parts.append("เด่น: " + ", ".join(good))
    if bad:
        parts.append("อ่อน: " + ", ".join(bad))
    return " | ".join(parts) or "ปานกลางทุกด้าน"

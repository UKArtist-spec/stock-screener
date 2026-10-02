"""AI คัดกรองหุ้นเติบโต: จัดประเภท Stable / Explosive / Cyclical Growth และตอบ 4 คำถาม

1. Growth มาจาก Demand จริง หรือรอบสั้นชั่วคราว
2. Margin โตตามรายได้ไหม
3. Valuation แพงไปหรือยัง
4. ธุรกิจพึ่งเงินทุน หรือพึ่งรอบวัฏจักรมากแค่ไหน
+ ราคาอยู่เหนือหรือต่ำกว่าเส้น EMA100

ส่วนจัดประเภทเป็นกฎที่เขียนไว้ชัดเจน (ทำงานทันที ฟรี ทุกตัว) ส่วน ask_claude() ใช้โมเดล AI จริงวิเคราะห์เชิงลึกรายตัว (ต้องมี API key)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

STABLE, EXPLOSIVE, CYCLICAL, NONE = "Stable Growth", "Explosive Growth", "Cyclical Growth", "ยังไม่เข้าข่ายหุ้นเติบโต"
TYPES = [STABLE, EXPLOSIVE, CYCLICAL]
TYPE_TH = {
    STABLE: "โตสม่ำเสมอ คาดการณ์ได้ ผันผวนต่ำ",
    EXPLOSIVE: "โตแรงมาก (25%+ ต่อปี) ศักยภาพสูง แต่ความเสี่ยงและราคามักสูง",
    CYCLICAL: "โตตามรอบเศรษฐกิจหรือรอบอุตสาหกรรม จังหวะเข้าสำคัญกว่าตัวอื่น",
    NONE: "รายได้โตช้าหรือหดตัว ไม่ใช่หุ้นเติบโตตามนิยามนี้",
}
TYPE_COLOR = {STABLE: "#2a7d5a", EXPLOSIVE: "#7a3fb8", CYCLICAL: "#b0701c", NONE: "#4f5666"}

PASS, WATCH, FAIL = "ผ่านคัดกรอง", "เฝ้าดู", "ไม่ผ่าน"
VERDICT_COLOR = {PASS: "#1f7a4d", WATCH: "#8a6414", FAIL: "#8a2e2e"}

CHECKS = ["demand", "margin", "valuation", "dependency"]
CHECK_TH = {"demand": "Demand จริงไหม", "margin": "Margin โตตามรายได้", "valuation": "ราคาแพงหรือยัง",
            "dependency": "พึ่งเงินทุน/วัฏจักร"}

# น้ำหนักของแต่ละคำถาม ปรับตามประเภทหุ้น
TYPE_WEIGHTS = {
    STABLE: {"demand": 30, "margin": 25, "valuation": 30, "dependency": 15},
    EXPLOSIVE: {"demand": 35, "margin": 25, "valuation": 15, "dependency": 25},
    CYCLICAL: {"demand": 20, "margin": 20, "valuation": 25, "dependency": 35},
    NONE: {"demand": 30, "margin": 25, "valuation": 25, "dependency": 20},
}

CYCLICAL_SECTORS = {"Energy", "Basic Materials", "Consumer Cyclical", "Real Estate", "Industrials"}
STRONG_CYCLE_KW = ["oil", "gas", "steel", "aluminum", "copper", "gold", "silver", "mining", "metal", "chemical",
                   "auto", "airline", "homebuild", "residential construction", "shipping", "marine", "trucking",
                   "building materials", "paper", "lumber", "agricultur", "farm", "coal", "uranium", "memory",
                   "travel", "lodging", "resort", "casino", "recreational vehicle"]
MEDIUM_CYCLE_KW = ["semiconductor", "industrial", "machinery", "rail", "freight", "packaging", "restaurant",
                   "apparel", "retail", "leisure", "advertising", "staffing", "real estate", "reit", "bank", "capital markets"]


# ---------------------------------------------------------------- helpers
def _ip(x, xs, ys):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(np.interp(x, xs, ys))


def _clean(s):
    return None if s is None else s.dropna()


def _ratio(a, b):
    if a is None or b is None:
        return None
    df = pd.concat([a, b], axis=1).dropna()
    df = df[df.iloc[:, 1] != 0]
    return None if df.empty else df.iloc[:, 0] / df.iloc[:, 1]


def _yoy(s):
    s = _clean(s)
    if s is None or len(s) < 2:
        return []
    out = []
    for a, b in zip(s.iloc[:-1], s.iloc[1:]):
        if a and a > 0:
            out.append((b / a - 1) * 100)
    return out


def _cagr(s):
    s = _clean(s)
    if s is None or len(s) < 3 or s.iloc[0] <= 0 or s.iloc[-1] <= 0:
        return None
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / (len(s) - 1)) - 1) * 100


def _last(s):
    s = _clean(s)
    return None if s is None or s.empty else float(s.iloc[-1])


def _fmt(x, spec="{:.0f}"):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else spec.format(x)


# ---------------------------------------------------------------- คำถามที่ 1: Demand จริงหรือรอบสั้น
def check_demand(fin, info):
    rev = fin.get("revenue")
    yoy = _yoy(rev)
    cagr = _cagr(rev)
    if not yoy:
        return {"score": None, "verdict": "ข้อมูลรายได้ไม่พอ", "reasons": [], "cagr": None, "yoy": [], "recent": None}
    recent = info.get("revenueGrowth")
    recent = recent * 100 if isinstance(recent, (int, float)) else yoy[-1]
    pos = sum(1 for g in yoy if g > 0) / len(yoy)
    vol = float(np.std(yoy)) if len(yoy) >= 2 else 0.0
    gm = _ratio(fin.get("gross_profit"), rev)
    gm_chg = float((gm.iloc[-1] - gm.iloc[0]) * 100) if gm is not None and len(gm) >= 2 else None

    level = _ip(cagr if cagr is not None else np.mean(yoy), [0, 5, 15, 30], [0, 40, 80, 100])
    stab = _ip(vol, [3, 10, 25, 50], [100, 75, 35, 0])
    gm_s = _ip(gm_chg, [-5, 0, 3], [0, 60, 100]) if gm_chg is not None else 60
    score = 0.30 * pos * 100 + 0.30 * level + 0.25 * stab + 0.15 * gm_s

    reasons = []
    earlier = yoy[:-1]
    spike = len(earlier) >= 1 and yoy[-1] > 20 and yoy[-1] > 2.5 * max(np.median(earlier), 1) and max(earlier) < 8
    decel = cagr is not None and recent < cagr - 15
    if spike:
        score -= 15
        reasons.append(f"รายได้เพิ่งเร่งตัวแรงในปีล่าสุด ({yoy[-1]:.0f}%) หลังจากโตช้ามาก่อน อาจเป็นรอบสั้นหรือดีลครั้งเดียว")
    if decel:
        score -= 10
        reasons.append(f"การเติบโตล่าสุด ({recent:.0f}%) ชะลอลงชัดเจนจากค่าเฉลี่ย ({cagr:.0f}%)")
    downs = sum(1 for g in yoy if g < 0)
    if downs:
        reasons.append(f"มีปีที่รายได้หดตัว {downs} ปี จาก {len(yoy)} ปี")
    else:
        reasons.append(f"รายได้โตทุกปีที่มีข้อมูล ({len(yoy)} ปี)")
    if gm_chg is not None:
        reasons.append("อัตรากำไรขั้นต้นเพิ่มขึ้น แสดงว่าตั้งราคาได้ ลูกค้าต้องการจริง" if gm_chg > 1 else
                       ("อัตรากำไรขั้นต้นลดลง อาจต้องลดราคาเพื่อเร่งยอดขาย" if gm_chg < -2 else "อัตรากำไรขั้นต้นทรงตัว"))
    score = max(0.0, min(100.0, score))
    if cagr is not None and cagr < 3 and recent < 5:
        verdict = "การเติบโตอ่อน"
    elif spike:
        verdict = "เร่งตัวกะทันหัน ต้องพิสูจน์ว่าไม่ใช่รอบสั้น"
    elif not downs and vol > 20 and (cagr or 0) >= 25:
        verdict = "โตแรงมาก แต่ไม่สม่ำเสมอ"
    elif downs or vol > 20:
        verdict = "โตแบบขึ้นลงตามรอบ"
    elif score >= 70:
        verdict = "Demand จริง เติบโตต่อเนื่อง"
    else:
        verdict = "โตจริงแต่ยังไม่โดดเด่น"
    return {"score": score, "verdict": verdict, "reasons": reasons, "cagr": cagr, "yoy": yoy, "recent": recent,
            "vol": vol, "downs": downs}


# ---------------------------------------------------------------- คำถามที่ 2: Margin โตตามรายได้ไหม
def check_margin(fin, demand):
    rev = fin.get("revenue")
    om = _ratio(fin.get("ebit"), rev)
    if om is None or len(om) < 2:
        return {"score": None, "verdict": "ข้อมูลกำไรไม่พอ", "reasons": [], "om_last": None, "om_chg": None}
    om = om * 100
    om_last, om_chg = float(om.iloc[-1]), float(om.iloc[-1] - om.iloc[0])
    eps_g, rev_g = _cagr(fin.get("eps")), demand.get("cagr")
    lev = (eps_g - rev_g) if eps_g is not None and rev_g is not None else None
    score = 0.6 * _ip(om_chg, [-6, -2, 0, 3, 8], [0, 30, 55, 80, 100]) + 0.4 * (_ip(lev, [-15, 0, 10], [0, 50, 100]) if lev is not None else 50)
    reasons = [f"อัตรากำไรจากการดำเนินงาน {om.iloc[0]:.1f}% -> {om_last:.1f}% ({om_chg:+.1f} จุด)"]
    if lev is not None:
        reasons.append(f"กำไรต่อหุ้นโต {eps_g:.0f}%/ปี เทียบรายได้ {rev_g:.0f}%/ปี" +
                       (" (กำไรโตเร็วกว่ารายได้ = มี operating leverage)" if lev > 3 else ""))
    if om_last < 0:
        score = min(score, 45 if om_chg > 5 else 25)
        reasons.append("ยังขาดทุนจากการดำเนินงาน" + (" แต่ขาดทุนลดลงเร็ว" if om_chg > 5 else ""))
    rising_rev = (rev_g or 0) > 3
    if om_chg >= 2 and rising_rev:
        verdict = "Margin ขยายตามรายได้"
    elif om_chg <= -2 and rising_rev:
        verdict = "รายได้โตแต่ Margin หด (แข่งราคา/ต้นทุนพุ่ง)"
    elif om_chg <= -2:
        verdict = "Margin หดตัว"
    else:
        verdict = "Margin ทรงตัว"
    return {"score": max(0.0, min(100.0, score)), "verdict": verdict, "reasons": reasons, "om_last": om_last,
            "om_chg": om_chg, "om_series": om}


# ---------------------------------------------------------------- คำถามที่ 3: Valuation แพงไปหรือยัง
def check_valuation(fin, info, demand, margin, is_cyclical):
    pe = info.get("forwardPE") or info.get("trailingPE")
    pe = pe if isinstance(pe, (int, float)) and pe > 0 else None
    g = [x for x in (demand.get("cagr"), _cagr(fin.get("eps"))) if x is not None and x > 0]
    growth = float(np.mean(g)) if g else None
    peg = pe / min(growth, 40) if pe and growth else None
    fcf, mc = _last(fin.get("fcf")), info.get("marketCap")
    fy = fcf / mc * 100 if fcf is not None and mc else None
    evs = info.get("enterpriseToRevenue") if isinstance(info.get("enterpriseToRevenue"), (int, float)) else None
    parts, reasons = [], []
    if peg is not None:
        parts.append((_ip(peg, [0.8, 1.2, 2, 3], [100, 75, 35, 0]), 0.45))
        reasons.append(f"P/E {pe:.0f} เท่า เทียบการเติบโต {growth:.0f}%/ปี (PEG {peg:.1f})")
    if fy is not None:
        parts.append((_ip(fy, [0, 2, 4, 7], [0, 35, 70, 100]), 0.35))
        reasons.append(f"ผลตอบแทนเงินสดอิสระ (FCF yield) {fy:.1f}% ต่อปีที่ราคาปัจจุบัน")
    if evs is not None and growth:
        parts.append((_ip(evs / max(growth / 10, 0.5), [0.5, 1, 2, 4], [100, 70, 30, 0]), 0.20 if parts else 1.0))
        reasons.append(f"มูลค่ากิจการ {evs:.1f} เท่าของยอดขาย")
    if not parts:
        return {"score": None, "verdict": "ข้อมูลราคาไม่พอ", "reasons": reasons, "peg": None, "fcf_yield": None}
    score = sum(s * w for s, w in parts) / sum(w for _, w in parts)
    om = margin.get("om_series")
    if is_cyclical and pe and pe < 12 and om is not None and len(om) >= 3 and om.iloc[-1] >= om.max() - 0.5:
        score -= 20
        reasons.append("P/E ต่ำขณะที่อัตรากำไรอยู่จุดสูงสุดของรอบ อาจเป็นกับดัก (กำไรอาจลดลงเมื่อรอบกลับ)")
    score = max(0.0, min(100.0, score))
    verdict = ("ยังไม่แพงเมื่อเทียบการเติบโต" if score >= 65 else
               "ราคาสมเหตุสมผล สะท้อนอนาคตไปบางส่วน" if score >= 40 else "แพง ราคาสะท้อนอนาคตไปมากแล้ว")
    return {"score": score, "verdict": verdict, "reasons": reasons, "peg": peg, "fcf_yield": fy}


# ---------------------------------------------------------------- คำถามที่ 4: พึ่งเงินทุน / พึ่งวัฏจักร
def check_dependency(fin, info, demand, margin):
    rev = fin.get("revenue")
    reasons = []
    # --- เงินทุน
    cap = 0.0
    f = _clean(fin.get("fcf"))
    if f is not None and len(f):
        neg = float((f <= 0).mean())
        cap += 35 * neg
        if neg:
            reasons.append(f"เงินสดอิสระติดลบ {int(round(neg * len(f)))} ปี จาก {len(f)} ปี")
    capex = _ratio(fin.get("capex").abs() if fin.get("capex") is not None else None, rev)
    if capex is not None and len(capex):
        ci = float(capex.mean() * 100)
        cap += _ip(ci, [3, 8, 15, 25], [0, 10, 20, 25])
        if ci >= 10:
            reasons.append(f"ต้องลงทุนสินทรัพย์หนัก (capex ราว {ci:.0f}% ของยอดขาย)")
    ocf = _clean(fin.get("ocf"))
    if ocf is not None and len(ocf) and ocf.abs().sum() > 0:
        si = _clean(fin.get("stock_issued"))
        di, dr = _clean(fin.get("debt_issued")), _clean(fin.get("debt_repaid"))
        ext = (si.sum() if si is not None else 0) + max((di.sum() if di is not None else 0) + (dr.sum() if dr is not None else 0), 0)
        ext_ratio = float(ext / ocf.abs().sum())
        cap += _ip(ext_ratio, [0, 0.1, 0.3, 0.6], [0, 5, 15, 25])
        if ext_ratio > 0.2:
            reasons.append(f"ระดมทุนจากการออกหุ้น/กู้สุทธิ ราว {ext_ratio * 100:.0f}% ของเงินสดจากการดำเนินงาน")
    sh = _clean(fin.get("shares"))
    if sh is not None and len(sh) >= 3 and sh.iloc[0] > 0:
        dil = ((sh.iloc[-1] / sh.iloc[0]) ** (1 / (len(sh) - 1)) - 1) * 100
        cap += _ip(dil, [0, 2, 5], [0, 8, 15])
        if dil > 2:
            reasons.append(f"จำนวนหุ้นเพิ่มขึ้น {dil:.1f}% ต่อปี (ผู้ถือหุ้นเดิมถูกเจือจาง)")
    cap = min(100.0, cap)
    # --- วัฏจักร
    sector = str(info.get("sector") or "")
    industry = str(info.get("industry") or "").lower()
    strong = any(k in industry for k in STRONG_CYCLE_KW) or sector in {"Energy", "Basic Materials"}
    medium = any(k in industry for k in MEDIUM_CYCLE_KW) or sector in CYCLICAL_SECTORS
    cyc = 35 if strong else (20 if medium else 0)
    cyc += _ip(demand.get("vol", 0), [5, 15, 35], [0, 15, 30])
    cyc += 10 * min(demand.get("downs", 0), 2) / 2
    om = margin.get("om_series")
    if om is not None and len(om) >= 3:
        cyc += _ip(float(om.std()), [2, 6, 12], [0, 8, 15])
    beta = info.get("beta")
    if isinstance(beta, (int, float)):
        cyc += _ip(beta, [0.8, 1.3, 1.8], [0, 5, 10])
    cyc = min(100.0, cyc)
    if strong or medium:
        reasons.append(f"อยู่ในกลุ่มที่ผูกกับรอบเศรษฐกิจ ({info.get('industry') or sector})")
    if demand.get("vol", 0) > 15:
        reasons.append("ยอดขายผันผวนมากในแต่ละปี")
    lvl = lambda x: "ต่ำ" if x < 30 else ("กลาง" if x < 55 else "สูง")  # noqa: E731
    score = 100 - (0.55 * max(cap, cyc) + 0.45 * min(cap, cyc))
    verdict = f"พึ่งเงินทุน{lvl(cap)} · พึ่งวัฏจักร{lvl(cyc)}"
    if not reasons:
        reasons.append("สร้างเงินสดได้เอง ไม่ต้องพึ่งการระดมทุน และธุรกิจไม่ผูกกับรอบเศรษฐกิจชัดเจน")
    return {"score": max(0.0, score), "verdict": verdict, "reasons": reasons, "capital": cap, "cycle": cyc,
            "strong_cycle": strong}


# ---------------------------------------------------------------- EMA100
def ema_status(vs_ema):
    if vs_ema is None or pd.isna(vs_ema):
        return {"above": None, "label": "ไม่มีข้อมูล EMA100", "note": ""}
    if vs_ema < 0:
        return {"above": False, "label": f"ต่ำกว่า EMA100 ({vs_ema:.1f}%)",
                "note": "แนวโน้มราคาระยะกลางเป็นขาลง ควรรอให้ราคากลับมายืนเหนือเส้นก่อน"}
    if vs_ema <= 5:
        return {"above": True, "label": f"เหนือ EMA100 ใกล้เส้น (+{vs_ema:.1f}%)",
                "note": "ยังเป็นขาขึ้นและราคาย่อมาใกล้เส้น เป็นจุดที่ความเสี่ยงต่อผลตอบแทนดี"}
    return {"above": True, "label": f"เหนือ EMA100 (+{vs_ema:.1f}%)",
            "note": "แนวโน้มราคาระยะกลางเป็นขาขึ้น" + (" แต่ห่างเส้นมาก ระวังไล่ราคา" if vs_ema > 20 else "")}


# ---------------------------------------------------------------- รวมทั้งหมด
def classify(demand, dep):
    cagr, recent, downs = demand.get("cagr"), demand.get("recent"), demand.get("downs", 0)
    if demand.get("score") is None:
        return NONE, "ต่ำ"
    g = max(x for x in (cagr, recent, 0) if x is not None)
    cyc = dep.get("cycle", 0)
    if cyc >= 60 and (downs >= 1 or dep.get("strong_cycle")):
        return CYCLICAL, "สูง" if cyc >= 75 else "กลาง"
    if g >= 25:
        return EXPLOSIVE, "สูง" if (cagr or 0) >= 25 and downs == 0 else "กลาง"
    if cyc >= 55:
        return CYCLICAL, "กลาง"
    if (cagr or 0) >= 5 and (downs == 0 or ((recent or 0) >= 10 and cyc < 45)):
        return STABLE, "สูง" if downs == 0 and demand.get("vol", 99) < 10 else "กลาง"
    if (cagr or 0) >= 5 or (recent or 0) >= 10:
        return CYCLICAL, "ต่ำ"
    return NONE, "กลาง"


def analyze(fin: dict, info: dict, vs_ema100=None) -> dict:
    demand = check_demand(fin, info)
    margin = check_margin(fin, demand)
    dep = check_dependency(fin, info, demand, margin)
    gtype, conf = classify(demand, dep)
    val = check_valuation(fin, info, demand, margin, gtype == CYCLICAL)
    checks = {"demand": demand, "margin": margin, "valuation": val, "dependency": dep}
    w = TYPE_WEIGHTS[gtype]
    pairs = [(checks[k]["score"], w[k]) for k in CHECKS if checks[k]["score"] is not None]
    score = sum(s * x for s, x in pairs) / sum(x for _, x in pairs) if pairs else None
    ema = ema_status(vs_ema100)

    flags = []
    if score is None:
        verdict = FAIL
    else:
        verdict = PASS if score >= 70 else (WATCH if score >= 55 else FAIL)
        if gtype == NONE:
            verdict = FAIL
            flags.append("ไม่ใช่หุ้นเติบโต")
        if (demand["score"] or 0) < 40 and verdict != FAIL:
            verdict = FAIL
            flags.append("การเติบโตยังไม่น่าเชื่อถือ")
        if val["score"] is not None and val["score"] < 35 and verdict != FAIL:
            verdict = WATCH
            flags.append("ธุรกิจดีแต่ราคาแพง รอราคาย่อ")
        if gtype == EXPLOSIVE and dep.get("capital", 0) >= 55 and verdict != FAIL:
            verdict = WATCH
            flags.append("โตแรงแต่ยังต้องพึ่งเงินระดมทุน")
        if gtype == CYCLICAL and verdict != FAIL and ema["above"] is False:
            flags.append("รอบอาจยังไม่กลับตัว (ราคาต่ำกว่า EMA100)")
    entry = "-"
    if verdict != FAIL and ema["above"] is not None:
        entry = "เข้าเกณฑ์ + เหนือ EMA100" if ema["above"] else "เข้าเกณฑ์ แต่รอยืนเหนือ EMA100"
    return {"type": gtype, "confidence": conf, "score": score, "verdict": verdict, "flags": flags, "checks": checks,
            "ema": ema, "vs_ema100": vs_ema100, "entry": entry}


def narrative(t: str, a: dict) -> str:
    c = a["checks"]
    parts = [f"{t} จัดเป็น {a['type']} (ความมั่นใจ{a['confidence']}): {TYPE_TH[a['type']]}"]
    for k in CHECKS:
        if c[k].get("verdict"):
            parts.append(f"{CHECK_TH[k]}: {c[k]['verdict']}")
    if a["ema"]["label"]:
        parts.append(f"กราฟ: {a['ema']['label']} {a['ema']['note']}".strip())
    tail = f"สรุป: {a['verdict']}" + (f" ({', '.join(a['flags'])})" if a["flags"] else "")
    return " · ".join(parts) + " · " + tail


def one_liner(a: dict) -> str:
    c = a["checks"]
    bits = [c["demand"]["verdict"], c["margin"]["verdict"], c["valuation"]["verdict"]]
    return " · ".join(b for b in bits if b and "ไม่พอ" not in b)


# ---------------------------------------------------------------- AI จริง (Claude) วิเคราะห์เชิงลึกรายตัว
def build_payload(t: str, name: str, info: dict, a: dict) -> dict:
    c = a["checks"]
    r = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 2)  # noqa: E731
    return {
        "ticker": t, "name": name, "sector": info.get("sector"), "industry": info.get("industry"),
        "rule_based_type": a["type"], "rule_based_verdict": a["verdict"], "flags": a["flags"],
        "revenue_yoy_pct_by_year": [r(x) for x in c["demand"].get("yoy", [])],
        "revenue_cagr_pct": r(c["demand"].get("cagr")), "latest_quarter_revenue_growth_pct": r(c["demand"].get("recent")),
        "operating_margin_last_pct": r(c["margin"].get("om_last")), "operating_margin_change_pts": r(c["margin"].get("om_chg")),
        "peg": r(c["valuation"].get("peg")), "fcf_yield_pct": r(c["valuation"].get("fcf_yield")),
        "forward_pe": r(info.get("forwardPE")), "ev_to_sales": r(info.get("enterpriseToRevenue")), "beta": r(info.get("beta")),
        "capital_dependency_0_100": r(c["dependency"].get("capital")), "cycle_dependency_0_100": r(c["dependency"].get("cycle")),
        "price_vs_ema100_pct": r(a.get("vs_ema100")),
        "evidence": {k: c[k].get("reasons", []) for k in CHECKS},
    }


PROMPT = """คุณคือนักวิเคราะห์หุ้นเติบโตที่อธิบายให้นักลงทุนทั่วไปเข้าใจ ใช้ข้อมูล JSON ด้านล่างเท่านั้น
และความรู้ทั่วไปเกี่ยวกับธุรกิจของบริษัทนี้ (บอกชัดเจนเมื่อเป็นความรู้ทั่วไป ไม่ใช่ตัวเลขใน JSON)

ตอบเป็นภาษาไทย กระชับ ใช้หัวข้อตามนี้:
1. ประเภทการเติบโต: Stable / Explosive / Cyclical Growth เห็นด้วยกับการจัดประเภทของระบบหรือไม่ เพราะอะไร
2. Growth มาจาก Demand จริงหรือรอบสั้นชั่วคราว
3. Margin โตตามรายได้ไหม
4. Valuation แพงไปหรือยัง
5. ธุรกิจพึ่งเงินทุนหรือพึ่งรอบวัฏจักรมากแค่ไหน
6. กราฟเทียบ EMA100 บอกอะไร
7. ความเสี่ยงหลัก 2-3 ข้อ และสิ่งที่ต้องติดตามในงบไตรมาสหน้า
8. สรุปหนึ่งประโยค: ผ่านคัดกรอง / เฝ้าดู / ไม่ผ่าน

ห้ามแนะนำให้ซื้อหรือขาย ปิดท้ายด้วยประโยคว่าเป็นข้อมูลประกอบการตัดสินใจ ไม่ใช่คำแนะนำการลงทุน

ข้อมูล:
"""


def ask_claude(api_key: str, model: str, payload: dict, timeout: int = 90) -> str:
    import requests

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 1800,
              "messages": [{"role": "user", "content": PROMPT + json.dumps(payload, ensure_ascii=False, indent=1)}]},
        timeout=timeout,
    )
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:  # noqa: BLE001
            msg = r.text
        raise RuntimeError(f"Claude API ตอบกลับ {r.status_code}: {msg[:300]}")
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")

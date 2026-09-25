"""Quality-Growth Screener: จัดอันดับหุ้น/ETF สหรัฐตามเกณฑ์ 8 ข้อ
รัน:  streamlit run app.py
"""
import html as _html
import json
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import data as D
import scoring as S

st.set_page_config(page_title="Quality Growth Screener", layout="wide")

# กัน Streamlit Cloud ใช้โมดูลเก่าค้างในหน่วยความจำ และเตือนชัดเจนถ้าไฟล์บน GitHub ไม่ครบเวอร์ชัน
import importlib  # noqa: E402

S = importlib.reload(S)
D = importlib.reload(D)
if not hasattr(S, "CRITERIA_TH") or not hasattr(S, "plain_summary") or not hasattr(D, "GROUPS"):
    st.error("ไฟล์บน GitHub ไม่ครบเวอร์ชันใหม่: ต้องอัปโหลด app.py, scoring.py, data.py และ requirements.txt ทั้ง 4 ไฟล์พร้อมกัน "
             "แล้วกด Manage app > Reboot app")
    st.stop()
DEMO_ENV = os.environ.get("DEMO") == "1"


st.markdown("""<style>
.stApp {background: linear-gradient(135deg, #000000 0%, #08112a 40%, #14224a 72%, #2a1660 100%); background-attachment: fixed;}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stSidebar"] {background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.015));
    border-right: 1px solid rgba(255,255,255,.08); backdrop-filter: blur(6px);}
.block-container {background: linear-gradient(145deg, rgba(255,255,255,.055), rgba(255,255,255,.015));
    border: 1px solid rgba(255,255,255,.09); border-radius: 16px; padding: 2rem 2.2rem; margin-top: 1rem;
    box-shadow: 0 10px 40px rgba(0,0,0,.55);}
[data-testid="stMetric"] {background: linear-gradient(145deg, rgba(255,255,255,.07), rgba(255,255,255,.02));
    border: 1px solid rgba(255,255,255,.10); border-radius: 12px; padding: 12px 16px;}
[data-testid="stMetricValue"] {font-size: 1.9rem;}
.pick {background: linear-gradient(145deg, rgba(255,255,255,.08), rgba(255,255,255,.02)); border: 1px solid rgba(255,255,255,.12);
    border-radius: 14px; padding: 14px 16px; text-align: left; min-height: 178px;}
.pk-t {font-size: 1.35rem; font-weight: 700;} .pk-n {font-size: .78rem; opacity: .65; height: 1.1rem; overflow: hidden; white-space: nowrap;}
.pk-s {font-size: 2.3rem; font-weight: 800; line-height: 1.25;} .pk-r {font-size: .85rem; font-weight: 600;}
.pk-m {font-size: .78rem; opacity: .8; margin-top: 2px;} .pk-p {font-size: .9rem; margin-top: 6px;}
.vc {background: linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.02)); border: 1px solid rgba(255,255,255,.12);
    border-radius: 16px; padding: 16px 16px 10px 16px; margin-bottom: 6px; min-height: 330px;}
.vc-top {display: flex; justify-content: space-between; align-items: center; gap: 8px;}
.vc-t {font-size: 1.3rem; font-weight: 800; line-height: 1.1;} .vc-n {font-size: .76rem; opacity: .65; max-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.bd {display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: .72rem; font-weight: 600; margin: 8px 4px 0 0;}
.vc-p {font-size: 1.05rem; font-weight: 600; margin-top: 8px;} .vc-s {font-size: .78rem; opacity: .85; line-height: 1.45; min-height: 4.4em; margin-top: 4px;}
.vc-x {font-size: .72rem; opacity: .6;}
</style>""", unsafe_allow_html=True)


def tv_widget(kind: str, config: dict, height: int):
    """ฝังวิดเจ็ตฟรีของ TradingView (โหลดผ่านเบราว์เซอร์ของผู้ใช้ ไม่ผ่านเซิร์ฟเวอร์แอพ)"""
    src = f"https://s3.tradingview.com/external-embedding/embed-widget-{kind}.js"
    html = (f'<body style="margin:0;background:transparent"><div class="tradingview-widget-container" '
            f'style="height:{height}px;width:100%"><div class="tradingview-widget-container__widget" '
            f'style="height:100%;width:100%"></div><script type="text/javascript" src="{src}" async>'
            f'{json.dumps(config)}</script></div></body>')
    if hasattr(st, "iframe"):  # Streamlit ใหม่: components.html ถูกยกเลิกแล้ว
        st.iframe(html, height=height)
    else:
        components.html(html, height=height)


def tv_symbol(t: str) -> str:
    return t.replace("-", ".")  # BRK-B -> BRK.B


# ------------------------------------------------------------------ Watchlist ในลิงก์ (จำค่าได้ด้วย URL)
qp = st.query_params
if "universe" not in st.session_state and qp.get("wl"):
    st.session_state["universe"] = qp["wl"].replace(",", " ")
_w0 = dict(S.DEFAULT_WEIGHTS)
try:
    if qp.get("w"):
        _vals = [int(x) for x in qp["w"].split(",")]
        if len(_vals) == len(S.CRITERIA):
            _w0 = dict(zip(S.CRITERIA, _vals))
except ValueError:
    pass

# ------------------------------------------------------------------ Sidebar
with st.sidebar:
    st.header("ตั้งค่า")
    demo = st.toggle("โหมดข้อมูลจำลอง (demo)", value=DEMO_ENV, help="ใช้ทดสอบหน้าตาแอพ ไม่ใช่ข้อมูลจริง")
    st.markdown("**โหลดรายชื่อหุ้น**")

    def _load(label, fn):
        with st.spinner(f"กำลังโหลด {label}..."):
            try:
                lst, src = fn()
                st.session_state["universe"] = " ".join(lst)
                st.toast(f"โหลด {label} แล้ว {len(lst)} ตัว · แหล่งข้อมูล: {src}")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))

    if st.button("S&P 500", key="grp_sp500", width="stretch", help="หุ้น ~500 ตัว ครั้งแรกใช้เวลาหลายนาที"):
        _load("S&P 500", lambda: (D.load_sp500(), "Wikipedia/GitHub"))
    for name in D.GROUPS:
        if st.button(name, key=f"grp_{name}", width="stretch", help=f"ETF อ้างอิง: {D.GROUPS[name][0]}"):
            _load(name, lambda n=name: D.load_group(n))
    if st.button("ค่าเริ่มต้น", key="grp_default", width="stretch", help="กลับไปใช้รายชื่อตั้งต้น 40 ตัว"):
        st.session_state.pop("universe", None)
        if "wl" in st.query_params:
            del st.query_params["wl"]
    universe_txt = st.text_area("หุ้น/ETF ที่ต้องการสแกน (พิมพ์ ticker คั่นด้วยเว้นวรรค)", st.session_state.get("universe", " ".join(D.DEFAULT_UNIVERSE)), height=140)
    tickers = sorted({t.strip().upper() for t in universe_txt.replace(",", " ").split() if t.strip()})
    with st.expander("น้ำหนักเกณฑ์ (กดเพื่อปรับ)"):
        weights = {k: st.slider(f"{S.CRITERIA_TH[k]} ({k})", 0, 30, _w0[k]) for k in S.CRITERIA}
    if st.button("บันทึก Watchlist + น้ำหนักลงในลิงก์", key="save_wl", width="stretch",
                 help="จำรายชื่อและน้ำหนักไว้ใน URL ของหน้านี้ แล้วบุ๊กมาร์กลิงก์ไว้ เปิดครั้งหน้าจะได้ชุดเดิม"):
        if len(tickers) > 250:
            st.warning("รายชื่อยาวเกินไปสำหรับเก็บในลิงก์ (เกิน 250 ตัว)")
        else:
            st.query_params["wl"] = ",".join(tickers)
            st.query_params["w"] = ",".join(str(weights[k]) for k in S.CRITERIA)
            st.toast("บันทึกแล้ว: บุ๊กมาร์กลิงก์ของหน้านี้ไว้ เปิดครั้งหน้าจะได้รายชื่อและน้ำหนักชุดเดิม")
    refresh = st.select_slider("รีเฟรชราคาทุก (วินาที)", [15, 30, 60, 120, 300], value=60)
    min_score = st.slider("คะแนนรวมขั้นต่ำ", 0, 90, 0)

tv_widget("ticker-tape", {
    "symbols": [
        {"proName": "FOREXCOM:SPXUSD", "title": "S&P 500"}, {"proName": "FOREXCOM:NSXUSD", "title": "Nasdaq 100"},
        {"proName": "AMEX:VOO", "title": "VOO"}, {"proName": "NASDAQ:QQQM", "title": "QQQM"},
        {"proName": "NASDAQ:SMH", "title": "SMH"}, {"proName": "AMEX:GLDM", "title": "GLDM"},
        {"proName": "NASDAQ:NVDA", "title": "NVDA"}, {"proName": "NASDAQ:MSFT", "title": "MSFT"},
        {"proName": "NASDAQ:AAPL", "title": "AAPL"}, {"proName": "BITSTAMP:BTCUSD", "title": "BTC"}],
    "showSymbolLogo": True, "isTransparent": True, "displayMode": "adaptive", "colorTheme": "dark", "locale": "th_TH"}, 76)
st.title("Quality Growth Screener")
st.caption("ข้อมูลงบการเงินอัปเดตรายปี/ไตรมาส (แคช 12 ชม.) ส่วนราคารีเฟรชอัตโนมัติ · Yahoo ฟรีดีเลย์ประมาณ 15 นาที · ไม่ใช่คำแนะนำการลงทุน")

with st.expander("เริ่มต้นใช้งานใน 30 วินาที (กดเพื่ออ่าน)", expanded=not st.session_state.get("intro_seen")):
    st.markdown("""
**1. คะแนน 0-100 = คุณภาพของธุรกิจ** วัดจาก 8 ด้าน เช่น โตเร็วไหม กำไรดีไหม หนี้เยอะไหม ราคาแพงไหม ยิ่งสูงยิ่งดี (เขียว = ดี, เหลือง = กลาง, แดง = อ่อน)

**2. จังหวะราคา = ตอนนี้น่าจับตาไหม** แยกจากคะแนน หุ้นดีที่ราคาเพิ่งย่อลงมา คือจังหวะที่น่าสนใจ ส่วนตัวที่ราคาอยู่ในขาลงควรระวัง

**3. กดปุ่ม "ดูรายละเอียด + ข่าว" ใต้การ์ดใบไหนก็ได้** จะเห็นกราฟราคา ข่าว และคำอธิบายคะแนนแต่ละข้อเป็นภาษาง่าย ๆ

ETF คือกองทุนที่รวมหุ้นหลายตัวไว้ในตัวเดียว แอพนี้เป็นเครื่องมือคัดกรองเบื้องต้น ไม่ใช่คำแนะนำให้ซื้อหรือขาย
""")
st.session_state["intro_seen"] = True


# ------------------------------------------------------------------ Data
@st.cache_data(ttl=12 * 3600, show_spinner="กำลังดึงงบการเงิน...")
def get_fundamentals(tickers: tuple, demo: bool) -> dict:
    d = D.fetch_many(list(tickers), demo)
    # ETF: ดึงหุ้นใน top holdings เพิ่มเพื่อทำ look-through
    extra = {s for v in d.values() if v.get("holdings") for s in v["holdings"]} - set(d)
    if extra:
        d.update(D.fetch_many(sorted(extra), demo))
    return d


@st.cache_data(ttl=30, show_spinner=False)
def get_quotes(tickers: tuple, demo: bool) -> pd.DataFrame:
    return D.fetch_quotes(list(tickers), demo)


moat = D.load_moat_tags()


def score_entry(t: str, fund: dict) -> dict | None:
    d = fund.get(t)
    if not d or d.get("error"):
        return None
    if d["type"] == "ETF":
        hold = {s: w for s, w in (d.get("holdings") or {}).items() if s in fund and fund[s]["type"] == "EQUITY"}
        if not hold:
            return None
        tw = sum(hold.values())
        agg = {k: 0.0 for k in S.CRITERIA}
        cw = {k: 0.0 for k in S.CRITERIA}
        for s, w in hold.items():
            r = S.score_stock(fund[s]["fin"], fund[s]["info"], moat.get(s))
            for k, v in r["scores"].items():
                if v is not None:
                    agg[k] += v * w
                    cw[k] += w
        scores = {k: (agg[k] / cw[k] if cw[k] else None) for k in S.CRITERIA}
        return {"scores": scores, "metrics": {"Moat": f"look-through {len(hold)} ตัวใหญ่สุด (ครอบคลุม {tw*100:.0f}% ของพอร์ต)"}}
    return S.score_stock(d["fin"], d["info"], moat.get(t))


fund = get_fundamentals(tuple(tickers), demo)
scored = {t: score_entry(t, fund) for t in tickers}
scored = {t: v for t, v in scored.items() if v}
others = [t for t in tickers if t not in scored and fund.get(t, {}).get("type") == "ETF"]  # ETF ทอง/พันธบัตร ไม่มีงบให้ประเมิน
failed = [t for t in tickers if t not in scored and t not in others]

EXCH = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "PCX": "AMEX", "ASE": "AMEX", "BTS": "BATS"}


def tv_full(t: str) -> str:
    ex = EXCH.get((fund.get(t, {}).get("info") or {}).get("exchange"))
    sym = tv_symbol(t)
    return f"{ex}:{sym}" if ex else sym


def sector_of(t: str) -> str:
    d = fund[t]
    return "ETF" if d["type"] == "ETF" else (d["info"].get("sector") or "อื่น ๆ")


def earnings_of(t: str) -> str:
    try:
        dt = pd.Timestamp(fund[t].get("next_earnings")).normalize()
        days = (dt - pd.Timestamp.now().normalize()).days
    except Exception:  # noqa: BLE001
        return "-"
    return f"{dt:%d %b} (อีก {days} วัน)" if days >= 0 else "-"


def timing_of(t: str, q) -> str:
    if t not in q.index:
        return "-"
    r = q.loc[t]
    return S.timing(r.get("From 52w high %"), r.get("vs MA200 %"), r.get("RSI"))


q_all = get_quotes(tuple(list(scored) + others), demo)
all_sectors = sorted({sector_of(t) for t in list(scored) + others})
with st.sidebar:
    sector_sel = st.multiselect("กรองกลุ่มอุตสาหกรรม", all_sectors, placeholder="ทั้งหมด")


def in_sector(t: str) -> bool:
    return not sector_sel or sector_of(t) in sector_sel


# ------------------------------------------------------------------ KPI + Top 5
tots = {t: S.total_score(r["scores"], weights) for t, r in scored.items()}
ratings = {t: S.rating(tots[t], scored[t]["scores"].get("Valuation")) for t in scored}
vis = [t for t in scored if in_sector(t)]
top_now = [t for t in vis if ratings[t] == S.TOP]
zone_now = [t for t in top_now if timing_of(t, q_all).startswith(S.ZONE)]
valid = [tots[t] for t in vis if tots[t] is not None]
k1, k2, k3, k4 = st.columns(4)
k1.metric("สแกนทั้งหมด", len(vis) + len([o for o in others if in_sector(o)]))
k2.metric("ผ่านเกณฑ์เด่น", len(top_now), help="คะแนนรวม >= 75 และ Valuation >= 60")
k3.metric("เด่น + ย่อเข้าโซน", len(zone_now), help="ผ่านเกณฑ์เด่น และราคาย่อจากจุดสูงสุด 8-25% โดยยังเหนือ MA200")
k4.metric("คะแนนเฉลี่ย", f"{sum(valid) / len(valid):.0f}" if valid else "-")


# ------------------------------------------------------------------ helper: การ์ด / กราฟย่อ / เรดาร์
def earnings_days(t: str):
    try:
        d = (pd.Timestamp(fund[t].get("next_earnings")).normalize() - pd.Timestamp.now().normalize()).days
        return d if d >= 0 else None
    except Exception:  # noqa: BLE001
        return None


def spark_svg(vals) -> str:
    vals = [float(v) for v in vals if v is not None and not pd.isna(v)] if isinstance(vals, (list, tuple)) else []
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{i * 200 / (len(vals) - 1):.1f},{42 - (v - lo) / rng * 38:.1f}" for i, v in enumerate(vals))
    col = "#30a46c" if vals[-1] >= vals[0] else "#e5484d"
    return (f'<svg viewBox="0 0 200 44" preserveAspectRatio="none" style="width:100%;height:46px;margin-top:6px">'
            f'<polygon points="0,44 {pts} 200,44" fill="{col}" opacity=".16"/>'
            f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>')


BADGE = {S.TOP: "#1f7a4d", S.QUALITY_PRICEY: "#8a6414", "น่าติดตาม": "#2a5d9a", "ไม่ผ่านเกณฑ์": "#5b6270"}


def card_html(r: dict) -> str:
    t = r["Ticker"]
    tot = r.get("คะแนนรวม")
    has = tot is not None and not pd.isna(tot)
    col = "#30a46c" if has and tot >= 75 else ("#d29922" if has and tot >= 55 else "#e5484d")
    ring = (f'<div style="width:62px;height:62px;border-radius:50%;background:conic-gradient({col} {tot:.0f}%,rgba(255,255,255,.12) 0);'
            f'display:flex;align-items:center;justify-content:center"><div style="width:48px;height:48px;border-radius:50%;background:#0c1428;'
            f'display:flex;align-items:center;justify-content:center;font-weight:800;color:{col}">{tot:.0f}</div></div>') if has else ""
    status = r.get("สถานะ", "")
    b_status = f'<span class="bd" style="background:{BADGE.get(status, "#444b58")}">{_html.escape(str(status))}</span>' if has else \
        '<span class="bd" style="background:#444b58">ไม่มีคะแนนธุรกิจ</span>'
    tm = str(r.get("จังหวะราคา", "-"))
    tcol = "#1f7a4d" if tm.startswith(S.ZONE) else ("#a83a3a" if tm.startswith("ต่ำกว่า") else ("#8a6414" if tm.startswith("ย่อลึก") else "#3a4152"))
    b_time = f'<span class="bd" style="background:{tcol}">{_html.escape(tm)}</span>' if tm != "-" else ""
    etf = '<span class="bd" style="background:#4a3f78">ETF</span>' if fund[t]["type"] == "ETF" else ""
    chg_key = "Today %" if period == "รายวัน" else "1M %"
    price, chg, fh = r.get("Price"), r.get(chg_key), r.get("From 52w high %")
    ok = lambda x: x is not None and not pd.isna(x)  # noqa: E731
    pline = ""
    if ok(price):
        cc = "#30a46c" if ok(chg) and chg >= 0 else "#e5484d"
        pline = f'${price:,.2f}' + (f' <span style="color:{cc};font-size:.85rem">{chg:+.2f}% {"วันนี้" if period == "รายวัน" else "1 เดือน"}</span>' if ok(chg) else "")
    if t in scored:
        summ = S.plain_summary(scored[t]["scores"], tm)
    else:
        summ = "ETF ประเภทนี้ไม่ได้ถือหุ้น (ทอง/ตราสารหนี้/อื่น ๆ) จึงไม่มีคะแนนธุรกิจ ดูได้แค่ราคาและแนวโน้ม"
    extra = []
    if ok(fh):
        extra.append(f"ห่างจากจุดสูงสุด 1 ปี {fh:.0f}%")
    d = earnings_days(t)
    if d is not None and d <= 14:
        extra.append(f"ประกาศงบอีก {d} วัน")
    return (f'<div class="vc"><div class="vc-top"><div><div class="vc-t">{_html.escape(t)}</div>'
            f'<div class="vc-n">{_html.escape(str(r.get("ชื่อ", "")))}</div></div>{ring}</div>'
            f'<div>{b_status}{b_time}{etf}</div><div class="vc-p">{pline}</div>{spark_svg(r.get("1Y trend"))}'
            f'<div class="vc-s">{_html.escape(summ)}</div><div class="vc-x">{_html.escape(" · ".join(extra))}</div></div>')


def radar(scores: dict):
    labels = [S.CRITERIA_TH[k] for k in scores]
    vals = [scores[k] or 0 for k in scores]
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.bar_chart(pd.Series(dict(zip(labels, vals))), horizontal=True, height=300)
        return
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself",
                                    line=dict(color="#30a46c"), fillcolor="rgba(48,164,108,.30)"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 100], gridcolor="rgba(255,255,255,.15)", tickfont=dict(size=9)),
                                 angularaxis=dict(gridcolor="rgba(255,255,255,.15)")),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#E6EDF3"), margin=dict(l=80, r=80, t=20, b=20),
                      height=340, showlegend=False)
    st.plotly_chart(fig, width="stretch")


@st.dialog("รายละเอียดหุ้น", width="large")
def detail_dialog(sel: str):
    st.subheader(f"{sel} · {fund[sel]['name']}")
    tm = timing_of(sel, q_all)
    st.caption(f"กลุ่ม: {sector_of(sel)} · ประกาศงบครั้งถัดไป: {earnings_of(sel)}")
    if sel in scored:
        r = scored[sel]
        tot = tots[sel]
        st.markdown(f"**สรุปสั้น ๆ:** {S.plain_summary(r['scores'], tm)}")
        m1, m2, m3 = st.columns(3)
        m1.metric("คะแนนรวม", f"{tot:.0f}/100" if tot is not None else "-", help="คุณภาพธุรกิจโดยรวม 0-100")
        m2.metric("สถานะ", ratings[sel])
        m3.metric("จังหวะราคา", tm, help="ดูจากระยะที่ราคาย่อจากจุดสูงสุด และแนวโน้มเทียบเส้นค่าเฉลี่ย 200 วัน")
    c1, c2 = st.columns([3, 2])
    with c1:
        tv_widget("advanced-chart", {
            "autosize": True, "symbol": tv_full(sel), "interval": "D", "timezone": "Asia/Bangkok",
            "theme": "dark", "style": "1", "locale": "th_TH", "backgroundColor": "rgba(0,0,0,0)",
            "allow_symbol_change": True, "hide_side_toolbar": False, "support_host": "https://www.tradingview.com"}, 480)
    with c2:
        if sel in scored:
            radar(r["scores"])
        else:
            st.info("ETF ประเภทนี้ไม่มีงบการเงินให้คะแนน ดูได้เฉพาะกราฟและข่าว")
    if sel in scored:
        st.markdown("**คะแนนแต่ละด้าน แปลเป็นภาษาคน**")
        exp = pd.DataFrame(S.explain_rows(r["scores"], r["metrics"]), columns=["เกณฑ์", "คะแนน", "หมายความว่า"])
        st.dataframe(exp, hide_index=True, width="stretch",
                     column_config={"คะแนน": st.column_config.ProgressColumn("คะแนน", min_value=0, max_value=100, format="%.0f")})
        missing = [S.CRITERIA_TH[k] for k, v in r["scores"].items() if v is None]
        if missing:
            st.info("ไม่มีข้อมูลสำหรับ: " + ", ".join(missing) + " (ถูกตัดออกจากคะแนนรวมและปรับน้ำหนักใหม่)")
    st.markdown(f"**ข่าวของ {sel}**")
    tv_widget("timeline", {"feedMode": "symbol", "symbol": tv_full(sel), "isTransparent": True, "displayMode": "regular",
                           "width": "100%", "height": "100%", "colorTheme": "dark", "locale": "th_TH"}, 420)
    st.caption("คะแนนเป็นข้อมูลคัดกรองเบื้องต้น ไม่ใช่คำแนะนำให้ซื้อหรือขาย")


tab1, tab_heat, tab_news, tab3 = st.tabs(["Screener", "Heatmap ตลาด", "ข่าวตลาด", "คู่มือ & วิธีคิดคะแนน"])

# ------------------------------------------------------------------ Tab 1
with tab1:
    v1, v2 = st.columns(2)
    view_mode = v1.radio("มุมมอง", ["การ์ด", "ตาราง"], horizontal=True)
    period = v2.radio("รอบการดู", ["รายวัน", "รายเดือน"], horizontal=True,
                      help="รายวัน = แสดงการเปลี่ยนแปลงวันนี้ · รายเดือน = แสดงการเปลี่ยนแปลง 1 เดือน")
    f1, f2, f3 = st.columns(3)
    only_buy = f1.checkbox("เฉพาะ 'ผ่านเกณฑ์เด่น'", help="คะแนนรวม >= 75 และ Valuation >= 60")
    only_zone = f2.checkbox("เฉพาะที่ย่อเข้าโซน", help="ราคาย่อจากจุดสูงสุด 8-25% และยังเหนือ MA200")
    compact = f3.toggle("ตารางแบบย่อ", value=True, disabled=view_mode == "การ์ด", help="ซ่อนคอลัมน์คะแนน 8 เกณฑ์ (มีผลเฉพาะมุมมองตาราง)")

    @st.fragment(run_every=refresh)
    def table():
        q = get_quotes(tuple(list(scored) + others), demo)

        def base_row(t):
            row = {"Ticker": t, "ชื่อ": fund[t]["name"], "กลุ่ม": sector_of(t), "ประกาศงบ": earnings_of(t),
                   "จังหวะราคา": timing_of(t, q)}
            if t in q.index:
                row.update(q.loc[t].to_dict())
            return row

        rows = []
        for t, r in scored.items():
            if not in_sector(t):
                continue
            tot = S.total_score(r["scores"], weights)
            row = base_row(t)
            row.update({"คะแนนรวม": tot, "สถานะ": S.rating(tot, r["scores"].get("Valuation")),
                        "จุดเด่น / จุดอ่อน": S.highlights(r["scores"])})
            row.update({k: r["scores"].get(k) for k in S.CRITERIA})
            rows.append(row)
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Ticker", "คะแนนรวม", "สถานะ", "จังหวะราคา"])
        if not df.empty:
            df = df[df["คะแนนรวม"].notna() & (df["คะแนนรวม"] >= min_score)]
            if only_buy:
                df = df[df["สถานะ"] == S.TOP]
            if only_zone:
                df = df[df["จังหวะราคา"].astype(str).str.startswith(S.ZONE)]
            df = df.sort_values("คะแนนรวม", ascending=False)
        extra = []
        if min_score == 0 and not only_buy and not only_zone:
            for t in others:
                if in_sector(t):
                    row = base_row(t)
                    row.update({"คะแนนรวม": float("nan"), "สถานะ": "ไม่มีงบให้คะแนน (ทอง/ตราสารหนี้/อื่น ๆ)",
                                "จุดเด่น / จุดอ่อน": "ดูราคาและแนวโน้มเท่านั้น"})
                    extra.append(row)
        if extra:
            df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
        df = df.reset_index(drop=True)
        df.index += 1
        if df.empty:
            st.info("ไม่มีหุ้นที่ตรงเงื่อนไขตอนนี้ ลองผ่อนตัวกรองด้านบนหรือลดคะแนนขั้นต่ำ")
            return
        st.caption(f"อัปเดตล่าสุด {pd.Timestamp.now():%H:%M:%S} · แสดง {len(df)} จาก {len(scored) + len(others)} ตัว · เรียงจากคะแนนสูงไปต่ำ")

        # ---------------- มุมมองการ์ด
        if view_mode == "การ์ด":
            n_show = st.session_state.get("n_show", 24)
            recs = df.head(n_show).to_dict("records")
            for i in range(0, len(recs), 4):
                for c, r in zip(st.columns(4), recs[i:i + 4]):
                    c.markdown(card_html(r), unsafe_allow_html=True)
                    if c.button("ดูรายละเอียด + ข่าว", key=f"card_{r['Ticker']}", width="stretch"):
                        st.session_state["open_detail"] = r["Ticker"]
                        st.rerun()
            if len(df) > n_show and st.button(f"แสดงเพิ่มอีก 24 ตัว (เหลือ {len(df) - n_show})", key="more"):
                st.session_state["n_show"] = n_show + 24
                st.rerun(scope="fragment")
            return

        # ---------------- มุมมองตาราง
        move = (["Today %"] if period == "รายวัน" else ["1M %"]) + ["From 52w high %"]
        trend = ["1Y trend"]
        score_cols = ["คะแนนรวม"] + S.CRITERIA
        cols = ["Ticker", "คะแนนรวม", "สถานะ", "จังหวะราคา", "จุดเด่น / จุดอ่อน", "กลุ่ม", "ชื่อ", "Price"] + move + ["ประกาศงบ"] + trend
        if not compact:
            cols += S.CRITERIA + ["vs MA200 %", "RSI"]
        cols = [c for c in cols if c in df]
        cfg = {"Ticker": st.column_config.TextColumn("Ticker", pinned=True),
               "คะแนนรวม": st.column_config.NumberColumn("คะแนนรวม", pinned=True),
               "Price": st.column_config.NumberColumn("ราคา", format="$%.2f"),
               "From 52w high %": st.column_config.NumberColumn("ห่างจาก High 52 สัปดาห์", format="%.1f%%"),
               "vs MA200 %": st.column_config.NumberColumn("เทียบ MA200", format="%.1f%%"),
               "RSI": st.column_config.NumberColumn("RSI(14)", format="%.0f"),
               "1Y trend": st.column_config.LineChartColumn("แนวโน้ม 1 ปี"),
               "จุดเด่น / จุดอ่อน": st.column_config.TextColumn("จุดเด่น / จุดอ่อน", width="large")}
        cfg.update({k: st.column_config.NumberColumn(S.CRITERIA_TH[k]) for k in S.CRITERIA})
        for c in move:
            cfg.setdefault(c, st.column_config.NumberColumn(c, format="%.2f%%"))

        def shade(v):
            if v is None or pd.isna(v):
                return "background-color: rgba(128,128,128,.15)"
            if v >= 75:
                return "background-color: rgba(46,160,67,.45)"
            if v >= 55:
                return "background-color: rgba(210,153,34,.40)"
            return "background-color: rgba(248,81,73,.35)"

        def move_color(v):
            if v is None or pd.isna(v):
                return ""
            return "color: #2ea043" if v > 0 else ("color: #f85149" if v < 0 else "")

        view = df[cols]
        sc = [c for c in score_cols if c in view]
        styled = (view.style.map(shade, subset=sc)
                  .map(move_color, subset=[c for c in move if c in view and c != "From 52w high %"])
                  .format({c: "{:.0f}" for c in sc}, na_rep="-"))
        c_a, c_b = st.columns([5, 1])
        c_a.caption("คลิกช่องซ้ายสุดของแถว เพื่อเปิดหน้าต่างรายละเอียด กราฟ และข่าว")
        c_b.download_button("ดาวน์โหลด CSV", view.drop(columns=[c for c in trend if c in view]).to_csv(index=False).encode("utf-8-sig"),
                            file_name="screener.csv", mime="text/csv", width="stretch")
        ev = st.dataframe(styled, column_config=cfg, width="stretch", height=560,
                          on_select="rerun", selection_mode="single-row", key="tbl")
        rows_sel = list(ev.selection.rows) if ev is not None and ev.selection else []
        if rows_sel != st.session_state.get("_last_rows"):
            st.session_state["_last_rows"] = rows_sel
            if rows_sel:
                st.session_state["open_detail"] = view.iloc[rows_sel[0]]["Ticker"]
                st.rerun()

    table()
    if failed:
        st.warning(f"ดึงข้อมูลไม่ได้/ข้อมูลไม่พอ: {', '.join(failed)}")

# ------------------------------------------------------------------ Heatmap
def draw_heatmap(color_by: str, size_by: str):
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("ต้องติดตั้ง plotly เพื่อแสดงแผนที่")
        return
    recs = []
    for t in vis:
        if fund[t]["type"] != "EQUITY" or t not in q_all.index:
            continue
        val = {"เปลี่ยนแปลงวันนี้": q_all.loc[t, "Today %"], "เปลี่ยนแปลง 1 เดือน": q_all.loc[t, "1M %"], "คะแนนรวม": tots[t]}[color_by]
        if val is None or pd.isna(val):
            continue
        cap = fund[t]["info"].get("marketCap") or 0
        recs.append(dict(sec=sector_of(t), t=t, size=float(cap) if size_by == "มูลค่าตลาด" and cap > 0 else 1.0,
                         val=float(val), cap=cap, name=fund[t]["name"]))
    if len(recs) < 3:
        st.info("มีหุ้นน้อยเกินไปสำหรับแผนที่ กดปุ่มโหลดกลุ่มหุ้นด้านซ้าย เช่น S&P 500 หรือ Nasdaq 100 เพื่อเพิ่มหุ้น")
        return
    pct = color_by != "คะแนนรวม"
    rng = 3.0 if color_by == "เปลี่ยนแปลงวันนี้" else 10.0
    fmt = (lambda v: f"{v:+.1f}%") if pct else (lambda v: f"{v:.0f}")  # noqa: E731
    ids, labels, parents, values, colors, texts, hovers = [], [], [], [], [], [], []
    for sec in sorted({r["sec"] for r in recs}):
        ch = [r for r in recs if r["sec"] == sec]
        tw = sum(c["size"] for c in ch)
        ids.append(sec); labels.append(sec); parents.append(""); values.append(tw); texts.append("")
        colors.append(sum(c["val"] * c["size"] for c in ch) / tw); hovers.append(f"{sec} · {len(ch)} ตัว")
        for c in ch:
            t = c["t"]
            ids.append(f"{sec}/{t}"); labels.append(t); parents.append(sec); values.append(c["size"]); colors.append(c["val"])
            texts.append(fmt(c["val"]))
            tot = tots.get(t)
            hovers.append(f"<b>{t}</b> · {_html.escape(str(c['name']))}<br>{sec}"
                          + (f"<br>คะแนนรวม {tot:.0f} · {ratings[t]}" if tot is not None else "")
                          + f"<br>วันนี้ {q_all.loc[t, 'Today %']:+.2f}% · 1 เดือน {q_all.loc[t, '1M %']:+.1f}%"
                          + (f"<br>มูลค่าตลาด ${c['cap'] / 1e9:,.0f} พันล้าน" if c["cap"] else ""))
    scale = ([[0, "#e5484d"], [0.5, "#2a2f3d"], [1, "#30a46c"]] if pct else [[0, "#e5484d"], [0.55, "#d29922"], [1, "#30a46c"]])
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, text=texts, hovertext=hovers, branchvalues="total",
        texttemplate="<b>%{label}</b><br>%{text}", hovertemplate="%{hovertext}<extra></extra>", textposition="middle center",
        textfont=dict(size=15, color="white"), pathbar=dict(visible=False), root_color="rgba(0,0,0,0)", tiling=dict(pad=3, packing="squarify"),
        marker=dict(colors=colors, colorscale=scale, cmin=-rng if pct else 0, cmax=rng if pct else 100,
                    pad=dict(t=28, l=3, r=3, b=3), line=dict(width=1.5, color="#0b1224"),
                    colorbar=dict(title=dict(text="% เปลี่ยนแปลง" if pct else "คะแนน"), thickness=12, len=0.6))))
    fig.update_layout(height=720, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#E6EDF3"))
    st.plotly_chart(fig, width="stretch")


with tab_heat:
    hm = st.radio("แผนที่", ["หุ้นที่สแกน (อ่านง่าย)", "ทั้งตลาดจาก TradingView"], horizontal=True)
    if hm.startswith("หุ้นที่สแกน"):
        h1, h2 = st.columns(2)
        color_by = h1.radio("สีแสดง", ["เปลี่ยนแปลงวันนี้", "เปลี่ยนแปลง 1 เดือน", "คะแนนรวม"], horizontal=True)
        size_by = h2.radio("ขนาดกรอบ", ["มูลค่าตลาด", "เท่ากันทุกตัว"], horizontal=True)
        st.caption("แต่ละกรอบคือหุ้น 1 ตัว จัดกลุ่มตามอุตสาหกรรม · เขียว = ขึ้นหรือคะแนนสูง, แดง = ลงหรือคะแนนต่ำ · "
                   "กรอบใหญ่ = บริษัทใหญ่ · เลื่อนเมาส์ดูรายละเอียด · ETF ไม่แสดงในแผนที่นี้ · อยากเห็นทั้งตลาดให้กดปุ่ม S&P 500 ที่แถบซ้าย")
        draw_heatmap(color_by, size_by)
    else:
        src = st.radio("ตลาด", ["S&P 500", "Nasdaq 100"], horizontal=True)
        tv_widget("stock-heatmap", {
            "dataSource": "SPX500" if src == "S&P 500" else "NASDAQ100", "grouping": "sector", "blockSize": "market_cap_basic",
            "blockColor": "change", "locale": "th_TH", "colorTheme": "dark", "hasTopBar": True, "isDataSetEnabled": False,
            "isZoomEnabled": True, "hasSymbolTooltip": True, "isMonoSize": False, "width": "100%", "height": "100%"}, 760)
        st.caption("แผนที่ทั้งตลาดมีหุ้นเป็นร้อยตัว กรอบจึงเล็ก ใช้เมาส์ล้อเลื่อนซูมเข้าไปดูกลุ่มที่สนใจได้")

with tab_news:
    n1, n2 = st.columns([3, 2])
    with n1:
        st.subheader("ข่าวตลาดหุ้นล่าสุด")
        tv_widget("timeline", {"feedMode": "market", "market": "stock", "isTransparent": True, "displayMode": "regular",
                               "width": "100%", "height": "100%", "colorTheme": "dark", "locale": "th_TH"}, 640)
    with n2:
        st.subheader("ปฏิทินเศรษฐกิจสหรัฐ")
        tv_widget("events", {"colorTheme": "dark", "isTransparent": True, "width": "100%", "height": "100%", "locale": "th_TH",
                             "importanceFilter": "-1,0,1", "countryFilter": "us"}, 640)
    st.caption("ข่าวเป็นข้อมูลประกอบการตัดสินใจ ไม่ได้ถูกนำไปคิดคะแนน · ข่าวส่วนใหญ่เป็นภาษาอังกฤษ")

# ------------------------------------------------------------------ คู่มือ
with tab3:
    st.markdown("""
### อ่านแอพนี้ใน 3 ขั้นตอน
1. **ดูคะแนนรวม (0-100)** คือคุณภาพของธุรกิจ เขียวคือดี เหลือคือกลาง แดงคืออ่อน
2. **ดูจังหวะราคา** ว่าตอนนี้ราคาอยู่ตรงไหน หุ้นดีที่เพิ่งย่อลงมาน่าจับตากว่าตัวที่ราคาวิ่งขึ้นสุดขีด
3. **กดดูรายละเอียดและข่าว** ก่อนตัดสินใจทุกครั้ง โดยเฉพาะตัวที่ราคาย่อลึกหรือใกล้ประกาศงบ

### ศัพท์ที่เจอบ่อย
| คำ | แปลว่า |
|---|---|
| ETF | กองทุนที่รวมหุ้นหลายตัวไว้ในตัวเดียว ซื้อขายในตลาดหุ้นได้เหมือนหุ้นตัวหนึ่ง |
| EPS | กำไรต่อหุ้น |
| ROIC | เงินลงทุนของบริษัท 100 บาท สร้างกำไรได้ปีละกี่บาท ยิ่งสูงยิ่งบริหารเงินเก่ง |
| Margin | ขายของ 100 บาท เหลือกำไรกี่บาท |
| FCF (เงินสดอิสระ) | เงินสดที่เหลือจริงหลังลงทุนต่อ เป็นเงินที่จ่ายปันผล ซื้อหุ้นคืน หรือใช้หนี้ได้ |
| SBC | ค่าตอบแทนพนักงานที่จ่ายเป็นหุ้น ทำให้ผู้ถือหุ้นเดิมถูกเจือจาง |
| Moat | ปราการที่ทำให้คู่แข่งแย่งลูกค้ายาก เช่น คนใช้เยอะจนต้องใช้ตาม, ย้ายค่ายลำบาก |
| P/E, PEG | ราคาหุ้นเป็นกี่เท่าของกำไร (PEG ปรับตามความเร็วการโต ต่ำกว่า ~1.2 ถือว่าไม่แพง) |
| MA200 | ราคาเฉลี่ย 200 วัน ถ้าราคาอยู่ต่ำกว่า แปลว่าแนวโน้มยังเป็นขาลง |
| RSI | ตัวชี้วัดว่าราคาลงแรงเกินไปหรือยัง ต่ำกว่า 30-40 คือลงมาเยอะ |

---
**แต่ละเกณฑ์ให้คะแนน 0-100 แล้วถ่วงน้ำหนักตามแถบด้านซ้าย** (ใช้งบรายปีย้อนหลัง ~4 ปีจาก Yahoo Finance)

น้ำหนักตั้งต้น: Revenue 12 · EPS 12 · ROIC 15 · Margin 10 · FCF 15 · Balance Sheet 8 · Moat 10 · Valuation 18

| เกณฑ์ | ตัววัด | ได้คะแนนเต็มเมื่อ |
|---|---|---|
| Revenue Growth | CAGR รายได้ | >= 22% (15% ได้ ~70) |
| EPS Growth | CAGR EPS หักถ้าจำนวนหุ้นเพิ่ม (เจือจาง) > 1%/ปี บวกเล็กน้อยถ้าซื้อหุ้นคืน | >= 28% (18% ได้ ~70) ขาดทุน = 0 |
| ROIC | NOPAT / (หนี้+ทุน-เงินสด) เฉลี่ย หักคะแนนถ้าผันผวน | เฉลี่ย >= 30% และนิ่ง (20% ได้ ~70) |
| Margin | Operating margin ล่าสุด 60% + แนวโน้มขยาย 40% | >= 40% และขยายตัว |
| FCF | CAGR FCF 60% + สัดส่วนปีที่ FCF โต 40% แล้วหักถ้า SBC สูงเกิน 15% ของ FCF หรือ FCF แปลงเป็นกำไรสุทธิได้ต่ำกว่า 70% | CAGR >= 20% โตทุกปี และคุณภาพ FCF ดี |
| Balance Sheet | หนี้สุทธิ / FCF (กี่ปีล้างหนี้) + interest coverage | เงินสดสุทธิ |
| Moat | แท็กที่คุณระบุใน moat.json 50% + proxy (Gross margin สูงและนิ่ง, ROIC) 50% (แท็กตั้งต้นเป็นการเดาเบื้องต้น ควรแก้ตามมุมมองของคุณ) | มีหลายแท็ก + margin/ROIC สูง |
| Valuation | PEG (Forward P/E / ค่าเฉลี่ยการโตของ EPS และรายได้) 40% + FCF yield 60% | PEG <= 0.8 และ FCF yield >= 7% |

**กลุ่มการเงิน (ธนาคาร/ประกัน):** ROIC, Margin, FCF และ Balance Sheet วัดไม่ได้ตามเกณฑ์นี้ จึงถูกตัดออกและปรับน้ำหนักใหม่

**สถานะ (วัดคุณภาพธุรกิจ):** 'ผ่านเกณฑ์เด่น' = คะแนนรวม >= 75 และ Valuation >= 60 · 'คุณภาพดี แต่ราคาตึง' = คะแนนรวม >= 75 แต่ Valuation ต่ำ · 'น่าติดตาม' = 60-74

**จังหวะราคา (แยกจากคะแนนคุณภาพ):** 'ย่อตัวเข้าโซน' = ราคาต่ำกว่าจุดสูงสุด 52 สัปดาห์ 8-25% และยังเหนือ MA200 · 'ใกล้จุดสูงสุด' = ห่างไม่ถึง 8% · 'ต่ำกว่า MA200 (ระวัง)' = แนวโน้มขาลง · 'ย่อลึก ตรวจสอบสาเหตุ' = ลงเกิน 25% ควรอ่านข่าวก่อน

**ETF:** ให้คะแนนแบบ look-through คือถัวเฉลี่ยตามน้ำหนักของหุ้น top holdings (ตามที่ Yahoo ให้ ปกติ ~10 ตัว)

**ข้อจำกัดที่ควรรู้:** Moat วัดจากตัวเลขตรง ๆ ไม่ได้ จึงพึ่งวิจารณญาณของคุณ · งบรายปีของ Yahoo มีแค่ ~4 ปี CAGR จึงเป็น 3 ช่วง · แอพนี้เป็นตัวคัดกรองเบื้องต้น ไม่ใช่คำแนะนำการลงทุน
""")

# เปิดหน้าต่างรายละเอียดหลังผู้ใช้กดการ์ด/แถว (ทำครั้งเดียวต่อการคลิก)
_open = st.session_state.pop("open_detail", None)
if _open and (_open in scored or _open in others):
    detail_dialog(_open)

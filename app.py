"""Quality-Growth Screener: จัดอันดับหุ้น/ETF สหรัฐตามเกณฑ์ 8 ข้อ
รัน:  streamlit run app.py
"""
import json
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import data as D
import scoring as S

st.set_page_config(page_title="Quality Growth Screener", layout="wide")
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
        weights = {k: st.slider(k, 0, 30, _w0[k]) for k in S.CRITERIA}
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

# ------------------------------------------------------------------ KPI
tots = {t: S.total_score(r["scores"], weights) for t, r in scored.items()}
ratings = {t: S.rating(tots[t], scored[t]["scores"].get("Valuation")) for t in scored}
valid = [v for v in tots.values() if v is not None]
k1, k2, k3, k4 = st.columns(4)
k1.metric("สแกนทั้งหมด", len(scored) + len(others))
k2.metric("น่าซื้อ", sum(1 for v in ratings.values() if v == "น่าซื้อ"))
k3.metric("คุณภาพดี แต่ราคาตึง", sum(1 for v in ratings.values() if v == "คุณภาพดี แต่ราคาตึง"))
k4.metric("คะแนนเฉลี่ย", f"{sum(valid) / len(valid):.0f}" if valid else "-")

tab1, tab_heat, tab3 = st.tabs(["Screener", "Heatmap ตลาด", "วิธีคิดคะแนน"])

# ------------------------------------------------------------------ Tab 1
with tab1:
    period = st.radio("รอบการดู", ["รายวัน", "รายเดือน"], horizontal=True,
                      help="รายวัน = เรียงตามคะแนน แสดงการเปลี่ยนแปลงวันนี้ · รายเดือน = แสดงการเปลี่ยนแปลง 1 เดือน และระยะห่างจากจุดสูงสุด 52 สัปดาห์")
    only_buy = st.checkbox("แสดงเฉพาะ 'น่าซื้อ' (คะแนนรวม >= 75 และ Valuation >= 60)")

    @st.fragment(run_every=refresh)
    def table():
        q = get_quotes(tuple(list(scored) + others), demo)
        rows = []
        for t, r in scored.items():
            tot = S.total_score(r["scores"], weights)
            row = {"Ticker": t, "ชื่อ": fund[t]["name"], "คะแนนรวม": tot,
                   "สถานะ": S.rating(tot, r["scores"].get("Valuation")),
                   "จุดเด่น / จุดอ่อน": S.highlights(r["scores"])}
            row.update({k: r["scores"].get(k) for k in S.CRITERIA})
            if t in q.index:
                row.update(q.loc[t].to_dict())
            rows.append(row)
        df = pd.DataFrame(rows)
        df = df[df["คะแนนรวม"].notna() & (df["คะแนนรวม"] >= min_score)]
        extra = []
        if min_score == 0 and not only_buy:
            for t in others:
                row = {"Ticker": t, "ชื่อ": fund[t]["name"], "คะแนนรวม": float("nan"),
                       "สถานะ": "ไม่มีงบให้คะแนน (ทอง/ตราสารหนี้/อื่น ๆ)", "จุดเด่น / จุดอ่อน": "ดูราคาและแนวโน้มเท่านั้น"}
                if t in q.index:
                    row.update(q.loc[t].to_dict())
                extra.append(row)
        if only_buy:
            df = df[df["สถานะ"] == "น่าซื้อ"]
        df = df.sort_values("คะแนนรวม", ascending=False)
        if extra:
            df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
        df = df.reset_index(drop=True)
        df.index += 1
        move = ["Today %"] if period == "รายวัน" else ["1M %"]
        move += [c for c in ["From 52w high %"] if c in df]
        trend = ["1Y trend"] if "1Y trend" in df else []
        score_cols = ["คะแนนรวม"] + S.CRITERIA
        cols = ["Ticker", "คะแนนรวม", "สถานะ", "จุดเด่น / จุดอ่อน", "ชื่อ", "Price"] + [c for c in move if c in df] + trend + S.CRITERIA
        cfg = {"Ticker": st.column_config.TextColumn("Ticker", pinned=True),
               "คะแนนรวม": st.column_config.NumberColumn("คะแนนรวม", pinned=True),
               "Price": st.column_config.NumberColumn("ราคา", format="$%.2f"),
               "From 52w high %": st.column_config.NumberColumn("ห่างจาก High 52 สัปดาห์", format="%.1f%%"),
               "1Y trend": st.column_config.LineChartColumn("แนวโน้ม 1 ปี"),
               "จุดเด่น / จุดอ่อน": st.column_config.TextColumn("จุดเด่น / จุดอ่อน", width="large")}
        for c in move:
            cfg.setdefault(c, st.column_config.NumberColumn(c, format="%.2f%%"))

        def shade(v):  # สีโปร่งแสง ใช้ได้ทั้งโหมดสว่าง/มืด
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
        fmt = {c: "{:.0f}" for c in score_cols}
        styled = (view.style.map(shade, subset=score_cols)
                  .map(move_color, subset=[c for c in move if c != "From 52w high %"])
                  .format(fmt, na_rep="-"))
        st.caption(f"อัปเดตล่าสุด {pd.Timestamp.now():%H:%M:%S} · แสดง {len(df)} จาก {len(scored) + len(others)} ตัว · "
                   "สีเขียว >= 75 · เหลือง 55-74 · แดง < 55")
        c_a, c_b = st.columns([5, 1])
        c_a.caption("คลิกช่องซ้ายสุดของแถว เพื่อดูกราฟและรายละเอียดด้านล่างตาราง")
        c_b.download_button("ดาวน์โหลด CSV", view.drop(columns=trend).to_csv(index=False).encode("utf-8-sig"),
                            file_name="screener.csv", mime="text/csv", width="stretch")
        ev = st.dataframe(styled, column_config=cfg, width="stretch", height=560,
                          on_select="rerun", selection_mode="single-row", key="tbl")
        rows_sel = list(ev.selection.rows) if ev is not None and ev.selection else []
        if rows_sel != st.session_state.get("_last_rows"):
            st.session_state["_last_rows"] = rows_sel
            if rows_sel:
                st.session_state["sel"] = view.iloc[rows_sel[0]]["Ticker"]
                st.rerun()  # รีเฟรชทั้งหน้าเพื่อแสดงกราฟของตัวที่เลือก (ตารางเองรีเฟรชราคาโดยกราฟไม่ถูกโหลดใหม่)

    table()
    if failed:
        st.warning(f"ดึงข้อมูลไม่ได้/ข้อมูลไม่พอ: {', '.join(failed)}")

# ------------------------------------------------------------------ รายละเอียดตัวที่เลือก (อยู่ใต้ตารางใน tab Screener)
with tab1:
    sel = st.session_state.get("sel")
    if sel in scored or sel in others:
        st.subheader(f"{sel} · {fund[sel]['name']}")
        cc1, cc2 = st.columns([3, 2])
        with cc1:
            tv_widget("advanced-chart", {
                "autosize": True, "symbol": tv_symbol(sel), "interval": "D", "timezone": "Asia/Bangkok",
                "theme": "dark", "style": "1", "locale": "th_TH", "backgroundColor": "rgba(0,0,0,0)",
                "allow_symbol_change": True, "hide_side_toolbar": False, "support_host": "https://www.tradingview.com"}, 560)
        with cc2:
            if sel in scored:
                r = scored[sel]
                tot = tots[sel]
                st.metric("คะแนนรวม", f"{tot:.0f}/100" if tot is not None else "-", ratings[sel])
                st.bar_chart(pd.Series({k: (v or 0) for k, v in r["scores"].items()}), horizontal=True, height=300)
                m = {k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in r["metrics"].items() if v is not None}
                st.dataframe(pd.DataFrame({"ค่า": m}), width="stretch")
                missing = [k for k, v in r["scores"].items() if v is None]
                if missing:
                    st.info("ไม่มีข้อมูลสำหรับ: " + ", ".join(missing) + " (ถูกตัดออกจากคะแนนรวมและปรับน้ำหนักใหม่)")
            else:
                st.info("ETF ประเภทนี้ (ทอง/ตราสารหนี้/อื่น ๆ) ไม่มีงบการเงินให้คะแนน ดูได้เฉพาะกราฟราคา")

with tab_heat:
    src = st.radio("ตลาด", ["S&P 500", "Nasdaq 100"], horizontal=True)
    tv_widget("stock-heatmap", {
        "dataSource": "SPX500" if src == "S&P 500" else "NASDAQ100", "grouping": "sector", "blockSize": "market_cap_basic",
        "blockColor": "change", "locale": "th_TH", "colorTheme": "dark", "hasTopBar": True, "isDataSetEnabled": False,
        "isZoomEnabled": True, "hasSymbolTooltip": True, "isMonoSize": False, "width": "100%", "height": "100%"}, 680)

# ------------------------------------------------------------------ Tab 3
with tab3:
    st.markdown("""
**แต่ละเกณฑ์ให้คะแนน 0-100 แล้วถ่วงน้ำหนักตามแถบด้านซ้าย** (ใช้งบรายปีย้อนหลัง ~4 ปีจาก Yahoo Finance)

| เกณฑ์ | ตัววัด | ได้คะแนนเต็มเมื่อ |
|---|---|---|
| Revenue Growth | CAGR รายได้ | >= 22% (15% ได้ ~70) |
| EPS Growth | CAGR EPS | >= 28% (18% ได้ ~70) ขาดทุน = 0 |
| ROIC | NOPAT / (หนี้+ทุน-เงินสด) เฉลี่ย หักคะแนนถ้าผันผวน | เฉลี่ย >= 30% และนิ่ง (20% ได้ ~70) |
| Margin | Operating margin ล่าสุด 60% + แนวโน้มขยาย 40% | >= 40% และขยายตัว |
| FCF | CAGR FCF 60% + สัดส่วนปีที่ FCF โต 40% | CAGR >= 20% โตทุกปี, FCF ติดลบ = ต่ำ |
| Balance Sheet | หนี้สุทธิ / FCF (กี่ปีล้างหนี้) + interest coverage | เงินสดสุทธิ |
| Moat | แท็กที่คุณระบุใน moat.json 50% + proxy (Gross margin สูงและนิ่ง, ROIC) 50% | มีหลายแท็ก + margin/ROIC สูง |
| Valuation | PEG (Forward P/E / EPS growth) 60% + FCF yield 40% | PEG <= 0.8 และ FCF yield >= 7% |

**สถานะ:** 'น่าซื้อ' = คะแนนรวม >= 75 และ Valuation >= 60 · 'คุณภาพดี แต่ราคาตึง' = คะแนนรวม >= 75 แต่ Valuation ต่ำ · 'น่าติดตาม' = 60-74

**ETF:** ให้คะแนนแบบ look-through คือถัวเฉลี่ยตามน้ำหนักของหุ้น top holdings (ตามที่ Yahoo ให้ ปกติ ~10 ตัว)

**ข้อจำกัดที่ควรรู้:** Moat วัดจากตัวเลขตรง ๆ ไม่ได้ จึงพึ่งวิจารณญาณของคุณ · งบรายปีของ Yahoo มีแค่ ~4 ปี CAGR จึงเป็น 3 ช่วง · เกณฑ์ 'ระยะยาว' ในความคิดคุณอาจอยากดู 5-10 ปี ซึ่งต้องเปลี่ยนแหล่งข้อมูล
""")

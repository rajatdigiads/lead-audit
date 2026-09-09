"""
Turquoise Digital — Lead & Customer Intelligence (Streamlit app, v2)
===================================================================
Two profiles in one tool:
  • Trades / Local-Service Leads  — score web-form leads (spam/dup/qualified)
  • Ecommerce / Customer List     — segment a customer DB by value + build
                                    Google Ads Customer Match files

Run:     streamlit run app.py
Deploy:  Render / Railway (custom domain) or share.streamlit.io
"""
import io
import csv
import json
import pandas as pd
import streamlit as st

from lead_quality_engine import process_batch, summarize
from core_io import build_column_map, rows_to_leads, ENGINE_FIELDS
from customer_list import detect_columns, analyze, build_exports

# ---- brand tokens ----------------------------------------------------------
INK, BODY, MUTED = "#0b1512", "#4a5551", "#64706b"
GREEN, GREEN_DK, DEEP = "#16d6a6", "#0fa98a", "#0a7a63"
MINT, MINT_BD = "#eefaf6", "#bfeade"
LIGHT, BORDER = "#f4f7f5", "#e2e6e3"
RED, AMBER = "#e5484d", "#e0a012"

st.set_page_config(page_title="Lead & Customer Intelligence · Turquoise Digital",
                   page_icon="🟢", layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Hanken+Grotesk:wght@400;500;600;700&display=swap');
/* Force LIGHT brand theme regardless of the viewer's Streamlit theme */
html, body, .stApp {{ color-scheme: light; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stHeader"], .main, .block-container {{ background:#ffffff !important; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{ background:{LIGHT} !important; }}
[data-testid="stSidebar"] * {{ color:{INK} !important; }}
[data-testid="stMetricLabel"] {{ color:{MUTED} !important; }}
html,body,[class*="css"],p,span,div,label,li {{ font-family:'Hanken Grotesk',sans-serif; color:{BODY}; }}
h1,h2,h3,h4 {{ font-family:'Archivo',sans-serif; font-weight:800; color:{INK}; letter-spacing:-0.03em; }}
[data-testid="stToolbar"], #MainMenu, footer, [data-testid="stDecoration"] {{ display:none !important; }}
.block-container {{ padding-top:2.2rem; max-width:1300px; }}
.eyebrow {{ font-family:'Archivo'; font-size:12.5px; font-weight:700; text-transform:uppercase;
           letter-spacing:0.12em; color:{DEEP}; margin-bottom:4px; }}
.hero {{ background:{MINT}; border:1px solid {MINT_BD}; border-radius:16px; padding:26px 30px; margin:6px 0 18px; }}
.bignum {{ font-family:'Archivo'; font-weight:900; font-size:52px; line-height:1; color:{INK}; }}
.sub {{ color:{MUTED}; font-size:15px; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid {BORDER}; border-radius:14px; padding:14px 16px; }}
div[data-testid="stMetricValue"] {{ font-family:'Archivo'; font-weight:800; color:{INK}; font-size:26px; }}
.stButton>button,.stDownloadButton>button {{ background:{GREEN}; color:{INK}; border:none; border-radius:9px;
    font-family:'Archivo'; font-weight:700; padding:9px 20px; }}
.stButton>button:hover,.stDownloadButton>button:hover {{ background:{GREEN_DK}; color:{INK}; }}
.card {{ background:#fff; border:1px solid {BORDER}; border-radius:14px; padding:18px 20px; margin-bottom:12px; }}
.action {{ background:{LIGHT}; border-left:4px solid {GREEN}; border-radius:10px; padding:12px 16px; margin:8px 0; }}
a.cta {{ display:inline-block; background:{GREEN}; color:{INK}!important; text-decoration:none;
        border-radius:9px; font-family:'Archivo'; font-weight:700; padding:11px 24px; }}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="eyebrow">Turquoise Digital · Lead & Customer Intelligence</div>', unsafe_allow_html=True)

# ---- sidebar: mode + config -----------------------------------------------
with st.sidebar:
    st.markdown("### 1. What is this data?")
    mode = st.radio("Profile", ["Trades / Local-service leads", "Ecommerce / Customer list"],
                    help="Trades = web-form leads. Ecommerce = a customer database export.")
    st.markdown("### 2. Client")
    client_name = st.text_input("Client / account name", "")

    if mode.startswith("Trades"):
        area_raw = st.text_area("Service area (suburbs / postcodes)",
                                "sydney, parramatta, bondi, manly, chatswood, penrith, nsw, 2000, 2150, 2026",
                                help="Leave blank for non-local businesses.")
        hours = st.slider("Business hours", 0, 23, (8, 18))
        cust_raw = st.text_area("Existing customers (email/phone, one per line)", "", height=70)
        existing = [{"email": l.strip()} if "@" in l else {"phone": l.strip()}
                    for l in cust_raw.splitlines() if l.strip()]
        trades_cfg = {
            "service_area_terms": [t.strip() for t in area_raw.replace("\n", ",").split(",") if t.strip()],
            "existing_customers": existing,
            "business_hours": (hours[0], hours[1]),
        }
    else:
        vip_orders = st.slider("VIP threshold (min orders)", 2, 20, 5)
        ec_cfg = {"vip_min_orders": vip_orders, "spend_top_pct": 0.90}

# ---- header ---------------------------------------------------------------
if mode.startswith("Trades"):
    st.markdown("# Lead-Quality Audit")
    st.markdown(f"<p style='font-size:16px;max-width:760px'>Most accounts don't have a traffic problem — they have "
                f"a <b style='color:{INK}'>measurement</b> problem. See how many recorded leads were real, "
                f"contactable jobs.</p>", unsafe_allow_html=True)
else:
    st.markdown("# Customer List Intelligence")
    st.markdown(f"<p style='font-size:16px;max-width:760px'>Your customer list is a <b style='color:{INK}'>media "
                f"asset</b>. See who your money actually comes from, and turn it into Google Ads Customer Match "
                f"audiences and exclusions.</p>", unsafe_allow_html=True)

uploaded = st.file_uploader("Upload CSV export", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV to run. Common column names are auto-detected; you can adjust the mapping after upload.")
    st.stop()

raw = uploaded.getvalue().decode("utf-8-sig")
rows = list(csv.DictReader(io.StringIO(raw)))
if not rows:
    st.error("That CSV appears to be empty."); st.stop()
headers = list(rows[0].keys())
df_raw = pd.DataFrame(rows)

def dl(df, label, fname):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=fname, mime="text/csv")

# ============================ TRADES MODE ==================================
if mode.startswith("Trades"):
    col_map = build_column_map(headers)
    with st.expander("Column mapping (auto-detected — adjust if needed)"):
        override, cols = {}, st.columns(3)
        opts = ["(none)"] + headers
        for i, f in enumerate(ENGINE_FIELDS):
            with cols[i % 3]:
                d = col_map.get(f, "(none)")
                c = st.selectbox(f, opts, index=opts.index(d) if d in opts else 0, key=f"m_{f}")
                if c != "(none)": override[f] = c
        col_map = build_column_map(headers, override)

    leads = rows_to_leads(rows, col_map)
    results = process_batch(leads, trades_cfg)
    s = summarize(results)

    who = f" for {client_name}" if client_name else ""
    st.markdown(f"""<div class="hero"><div class="eyebrow">What we found{who}</div>
      <span class="bignum">{s['total_leads']} → {s['real_leads']}</span>
      <div class="sub">Recorded <b>{s['total_leads']}</b> leads · <b style="color:{INK}">{s['real_leads']}</b> real ·
      <b style="color:{DEEP}">{s['qualified']}</b> qualified jobs. You paid for all {s['total_leads']}.</div></div>""",
      unsafe_allow_html=True)

    c = s["counts"]; m = st.columns(5)
    m[0].metric("Lead Quality", f"{s['lead_quality_pct']}%")
    m[1].metric("Real leads", s["real_leads"])
    m[2].metric("Spam + Dup", s["spam_and_duplicate"])
    m[3].metric("Qualified", s["qualified"])
    m[4].metric("Sales-ready", s["sales_ready"])

    st.markdown("### Where the leads went")
    order = ["qualified", "existing_customer", "unqualified", "duplicate", "spam"]
    lbl = {"qualified":"Qualified","existing_customer":"Existing","unqualified":"Unqualified","duplicate":"Duplicate","spam":"Spam"}
    st.bar_chart(pd.DataFrame({"Status":[lbl[k] for k in order],"Leads":[c.get(k,0) for k in order]}).set_index("Status"), color=GREEN)

    # --- campaign-level insight (the actionable part) ---
    st.markdown("### Lead quality by campaign")
    st.caption("Which campaigns send junk vs jobs — where to add negatives or shift budget.")
    camp = {}
    for r in results:
        cn = r.raw.get("campaign") or "(no campaign)"
        d = camp.setdefault(cn, {"total":0,"qualified":0,"spam":0,"unqualified":0,"duplicate":0,"existing_customer":0})
        d["total"] += 1; d[r.status] = d.get(r.status,0)+1
    crows = []
    for cn, d in camp.items():
        real = d["total"] - d["spam"] - d["duplicate"]
        crows.append({
            "Campaign": cn, "Leads": d["total"],
            "Qualified %": round(100*d["qualified"]/real,0) if real else 0,
            "Spam %": round(100*d["spam"]/d["total"],0) if d["total"] else 0,
            "Qualified": d["qualified"], "Spam": d["spam"], "Unqualified": d["unqualified"],
        })
    cdf = pd.DataFrame(crows).sort_values("Qualified %", ascending=False)
    st.dataframe(cdf, use_container_width=True, hide_index=True)
    if len(cdf) > 1:
        best, worst = cdf.iloc[0], cdf.iloc[-1]
        st.markdown(f'<div class="action">🟢 <b>{best["Campaign"]}</b> is your best source '
                    f'({int(best["Qualified %"])}% qualified). Push budget here.<br>'
                    f'🔴 <b>{worst["Campaign"]}</b> is weakest '
                    f'({int(worst["Qualified %"])}% qualified, {int(worst["Spam %"])}% spam). '
                    f'Add negatives / review before spending more.</div>', unsafe_allow_html=True)

    def group(title, statuses):
        g = [r for r in results if r.status in statuses]
        if not g: return
        st.markdown(f"#### {title} ({len(g)})")
        st.dataframe(pd.DataFrame([{
            "Lead": r.raw.get("name") or "(no name)", "Score": r.quality_score,
            "Campaign": r.raw.get("campaign","—"), "Why": " · ".join(r.reasons) or "—"
        } for r in sorted(g, key=lambda x:-x.quality_score)]), use_container_width=True, hide_index=True)
    group("✅ Qualified — chase these", ["qualified"])
    group("➖ Unqualified", ["unqualified"])
    group("♻️ Duplicates", ["duplicate"])
    group("🚫 Spam", ["spam"])

    st.markdown("### Export")
    scored = pd.DataFrame([dict(r.raw, status=r.status, quality_score=r.quality_score,
                                sales_ready=r.is_sales_ready, reasons=" | ".join(r.reasons)) for r in results])
    dl(scored, "⬇ Scored leads (CSV)", "scored_leads.csv")

# ============================ ECOMMERCE MODE ===============================
else:
    cmap = detect_columns(headers)
    with st.expander("Column mapping (auto-detected — adjust if needed)"):
        override, cols = {}, st.columns(3)
        opts = ["(none)"] + headers
        for i, f in enumerate(["email","phone","first","last","company","city","state","country","zip","spent","orders","date"]):
            with cols[i % 3]:
                d = cmap.get(f, "(none)")
                c = st.selectbox(f, opts, index=opts.index(d) if d in opts else 0, key=f"e_{f}")
                if c != "(none)": override[f] = c
        cmap = detect_columns(headers, override)

    if "spent" not in cmap and "orders" not in cmap:
        st.warning("No **Total Spent** or **Total Orders** column found — map one above. "
                   "Value segmentation needs at least one.")

    out, s, geo, city = analyze(df_raw, cmap, ec_cfg)
    who = f" for {client_name}" if client_name else ""
    st.markdown(f"""<div class="hero"><div class="eyebrow">Customer list{who}</div>
      <span class="bignum">${s['total_revenue']:,.0f}</span>
      <div class="sub">from <b style="color:{INK}">{s['buyers']}</b> buyers · your top 20% drive
      <b style="color:{DEEP}">{s['top20pct_revenue_share']}%</b> of revenue ·
      <b>{s['prospects_never_bought']}</b> signed up but never bought.</div></div>""", unsafe_allow_html=True)

    seg = s["segments"]; m = st.columns(5)
    m[0].metric("Total revenue", f"${s['total_revenue']:,.0f}")
    m[1].metric("Buyers", s["buyers"])
    m[2].metric("Repeat + VIP", s["repeat_or_vip"])
    m[3].metric("Never bought", seg.get("prospect", 0))
    m[4].metric("Avg order value", f"${s['avg_order_value']:,.0f}")

    st.markdown("### Customer segments")
    so = ["vip","repeat","one_time","prospect","junk"]
    sl = {"vip":"VIP","repeat":"Repeat","one_time":"One-time","prospect":"Never bought","junk":"Junk"}
    st.bar_chart(pd.DataFrame({"Segment":[sl[k] for k in so],"Customers":[seg.get(k,0) for k in so]}).set_index("Segment"), color=GREEN)

    cc = st.columns(2)
    with cc[0]:
        if len(geo):
            st.markdown("#### Revenue by region")
            st.caption("Where your buyers are — bid up these locations.")
            st.dataframe(geo.rename("Revenue $").round(0).reset_index().rename(columns={"_state":"Region"}),
                         use_container_width=True, hide_index=True)
    with cc[1]:
        st.markdown("#### List health")
        st.write(f"- **B2B (has company):** {s['b2b_with_company']}")
        st.write(f"- **Missing phone:** {s['missing_phone']} (no SMS/WhatsApp remarketing)")
        st.write(f"- **Junk/test records:** {s['junk_records']} (purge)")
        st.write(f"- **Possible duplicate people:** {s['duplicate_people_by_name']}")

    st.markdown("### What to do next (Google Ads)")
    st.markdown(f'<div class="action"><b>1. Customer Match — high-value seed.</b> Upload the '
                f'{s["repeat_or_vip"]} repeat+VIP buyers → feed value-based bidding & seed lookalike prospecting.</div>'
                f'<div class="action"><b>2. Exclude the {seg.get("prospect",0)} never-purchased</b> from '
                f'prospecting campaigns → stop paying to re-acquire your own list; remarket to them separately.</div>'
                f'<div class="action"><b>3. Win-back the {seg.get("one_time",0)} one-time buyers</b> → '
                f'cheapest revenue you have.</div>', unsafe_allow_html=True)

    st.markdown("### Segment breakdown")
    show = out[["_name","segment","_orders","_spent","why"]].rename(
        columns={"_name":"Customer","_orders":"Orders","_spent":"Spent","why":"Why"})
    st.dataframe(show.sort_values("Spent", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Export")
    exports = build_exports(out, cmap)
    e = st.columns(4)
    with e[0]: dl(out.drop(columns=[c for c in out.columns if c.startswith('_')]), "⬇ Segmented list", "segmented.csv")
    with e[1]: dl(exports["customer_match_high_value"], f"⬇ Customer Match: high-value ({len(exports['customer_match_high_value'])})", "customer_match_high_value.csv")
    with e[2]: dl(exports["customer_match_win_back"], f"⬇ Win-back ({len(exports['customer_match_win_back'])})", "customer_match_win_back.csv")
    with e[3]: dl(exports["exclusion_never_purchased"], f"⬇ Exclusion list ({len(exports['exclusion_never_purchased'])})", "exclusion_never_purchased.csv")
    st.caption("Customer Match files use Google's template columns (Email, Phone, First/Last Name, Country, Zip). "
               "Google hashes the data on upload.")

st.markdown("---")
st.markdown('<a class="cta" href="https://calendly.com/rajatdigiads/meetingrajat" target="_blank">Get a free audit</a>',
            unsafe_allow_html=True)
st.caption("Turquoise Digital · senior-led · month to month, no lock-in · no reporting theatre")

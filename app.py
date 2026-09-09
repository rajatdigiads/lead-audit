"""
Turquoise Digital — Lead-Quality Audit (Streamlit app)
======================================================
Drag in a client's lead export (CSV) -> instant lead-quality audit.
Positioning: "find the leak" — accounts that look healthy are usually
mis-measured, not underperforming.

Run locally:   streamlit run app.py
Deploy free:   push to GitHub -> share.streamlit.io
"""

import io
import csv
import json
import pandas as pd
import streamlit as st

from lead_quality_engine import process_batch, summarize
from core_io import build_column_map, rows_to_leads, ENGINE_FIELDS

# --- brand tokens -----------------------------------------------------------
INK = "#0b1512"
BODY = "#4a5551"
MUTED = "#64706b"
GREEN = "#16d6a6"
GREEN_DARK = "#0a7a63"
MINT_BG = "#eefaf6"
LIGHT_BG = "#f4f7f5"
BORDER = "#e2e6e3"
RED = "#e5484d"
AMBER = "#e0a012"

STATUS_COLORS = {
    "qualified": GREEN,
    "existing_customer": GREEN_DARK,
    "unqualified": AMBER,
    "duplicate": "#8b978f",
    "spam": RED,
}
STATUS_LABEL = {
    "qualified": "Qualified",
    "existing_customer": "Existing customer",
    "unqualified": "Unqualified",
    "duplicate": "Duplicate",
    "spam": "Spam",
}

st.set_page_config(page_title="Lead-Quality Audit · Turquoise Digital",
                   page_icon="🟢", layout="wide")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Hanken+Grotesk:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, p, span, div {{ font-family: 'Hanken Grotesk', sans-serif; color: {BODY}; }}
h1, h2, h3, h4 {{ font-family: 'Archivo', sans-serif; font-weight: 800; color: {INK}; letter-spacing: -0.03em; }}
.eyebrow {{ font-family:'Archivo'; font-size:12.5px; font-weight:700; text-transform:uppercase;
           letter-spacing:0.12em; color:{GREEN_DARK}; margin-bottom:6px; }}
.hero {{ background:{MINT_BG}; border:1px solid #bfeade; border-radius:16px; padding:28px 32px; margin:8px 0 20px; }}
.leak-num {{ font-family:'Archivo'; font-weight:900; font-size:56px; line-height:1; color:{INK}; }}
.leak-sub {{ color:{MUTED}; font-size:15px; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid {BORDER}; border-radius:14px; padding:14px 16px; }}
div[data-testid="stMetricValue"] {{ font-family:'Archivo'; font-weight:800; color:{INK}; }}
.stButton>button, .stDownloadButton>button {{ background:{GREEN}; color:{INK}; border:none;
    border-radius:9px; font-family:'Archivo'; font-weight:700; padding:10px 22px; }}
.stButton>button:hover, .stDownloadButton>button:hover {{ background:#0fa98a; color:{INK}; }}
.pill {{ display:inline-block; padding:2px 10px; border-radius:100px; font-size:11.5px; font-weight:700;
        border:1px solid {BORDER}; }}
.reason {{ color:{MUTED}; font-size:13px; }}
a.cta {{ display:inline-block; background:{GREEN}; color:{INK}!important; text-decoration:none;
        border-radius:9px; font-family:'Archivo'; font-weight:700; padding:11px 24px; }}
</style>
""", unsafe_allow_html=True)

# --- header -----------------------------------------------------------------
st.markdown('<div class="eyebrow">Turquoise Digital · Lead Intelligence</div>', unsafe_allow_html=True)
st.markdown("# Lead-Quality Audit")
st.markdown(
    f"<p style='font-size:17px;max-width:760px'>Most accounts don't have a traffic problem — they have a "
    f"<b style='color:{INK}'>measurement</b> problem. Drop in a lead export and see how many of the "
    f"leads Google counted as conversions were actually real, contactable jobs.</p>",
    unsafe_allow_html=True)

# --- sidebar: client config -------------------------------------------------
with st.sidebar:
    st.markdown("### Client setup")
    client_name = st.text_input("Client / account name", value="")
    area_raw = st.text_area(
        "Service area terms",
        value="sydney, parramatta, bondi, manly, chatswood, penrith, nsw, 2000, 2150, 2026",
        help="Suburbs & postcodes the client actually services. Leads with no match here can't be 'qualified'.")
    hours = st.slider("Business hours (local)", 0, 23, (8, 18))
    st.caption("Optional: paste known customers to catch repeat contacts.")
    cust_raw = st.text_area("Existing customers (email or phone, one per line)", value="", height=80)

    existing = []
    for line in cust_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "@" in line:
            existing.append({"email": line})
        else:
            existing.append({"phone": line})

    client_cfg = {
        "service_area_terms": [t.strip() for t in area_raw.replace("\n", ",").split(",") if t.strip()],
        "existing_customers": existing,
        "business_hours": (hours[0], hours[1]),
    }

# --- upload -----------------------------------------------------------------
uploaded = st.file_uploader("Upload lead export (CSV)", type=["csv"])

st.caption("No file yet? Grab the sample to see it work:")
try:
    with open("sample_real_leads.csv", "rb") as f:
        st.download_button("Download sample CSV", f, file_name="sample_real_leads.csv")
except FileNotFoundError:
    pass

if uploaded is None:
    st.info("Upload a CSV to run the audit. Columns like Name, Email, Phone, Message, Date, Suburb, Campaign are auto-detected.")
    st.stop()

# --- parse + map columns ----------------------------------------------------
raw = uploaded.getvalue().decode("utf-8-sig")
rows = list(csv.DictReader(io.StringIO(raw)))
if not rows:
    st.error("That CSV appears to be empty.")
    st.stop()
headers = list(rows[0].keys())
col_map = build_column_map(headers)

with st.expander("Column mapping (auto-detected — adjust if needed)", expanded=False):
    override = {}
    cols = st.columns(3)
    options = ["(none)"] + headers
    for i, field in enumerate(ENGINE_FIELDS):
        with cols[i % 3]:
            default = col_map.get(field, "(none)")
            choice = st.selectbox(field, options, index=options.index(default) if default in options else 0,
                                  key=f"map_{field}")
            if choice != "(none)":
                override[field] = choice
    col_map = build_column_map(headers, override)

for core in ("email", "phone"):
    if core not in col_map:
        st.warning(f"No **{core}** column detected — map it above for accurate duplicate/spam detection.")

# --- run engine -------------------------------------------------------------
leads = rows_to_leads(rows, col_map)
results = process_batch(leads, client_cfg)
s = summarize(results)

# --- hero "leak" line -------------------------------------------------------
title = f" for {client_name}" if client_name else ""
st.markdown(f"""
<div class="hero">
  <div class="eyebrow">What we found{title}</div>
  <span class="leak-num">{s['total_leads']} → {s['real_leads']}</span>
  <div class="leak-sub">The account recorded <b>{s['total_leads']}</b> leads. Only
  <b style="color:{INK}">{s['real_leads']}</b> were real, and just
  <b style="color:{GREEN_DARK}">{s['qualified']}</b> are qualified jobs worth chasing.
  You paid for all {s['total_leads']}.</div>
</div>
""", unsafe_allow_html=True)

# --- metric tiles -----------------------------------------------------------
c = s["counts"]
m = st.columns(5)
m[0].metric("Lead Quality", f"{s['lead_quality_pct']}%", help="Real leads ÷ total")
m[1].metric("Real leads", s["real_leads"], help="Excludes spam & duplicates")
m[2].metric("Spam + Duplicate", s["spam_and_duplicate"], delta=f"-{s['spam_and_duplicate']}", delta_color="inverse")
m[3].metric("Qualified", s["qualified"])
m[4].metric("Sales-ready", s["sales_ready"], help="Score ≥ 75")

# --- breakdown chart --------------------------------------------------------
st.markdown("### Where the leads went")
chart_df = pd.DataFrame({
    "Status": [STATUS_LABEL[k] for k in ["qualified", "existing_customer", "unqualified", "duplicate", "spam"]],
    "Leads": [c.get(k, 0) for k in ["qualified", "existing_customer", "unqualified", "duplicate", "spam"]],
}).set_index("Status")
st.bar_chart(chart_df, color=GREEN)

# --- categorized lead tables ------------------------------------------------
def show_group(title, statuses, tone=""):
    rows_g = [r for r in results if r.status in statuses]
    if not rows_g:
        return
    st.markdown(f"#### {title} ({len(rows_g)})")
    data = []
    for r in sorted(rows_g, key=lambda x: -x.quality_score):
        data.append({
            "Lead": r.raw.get("name") or "(no name)",
            "Score": r.quality_score,
            "Campaign": r.raw.get("campaign", "—"),
            "Why": " · ".join(r.reasons) if r.reasons else "—",
        })
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

show_group("✅ Qualified — chase these", ["qualified"])
show_group("🔁 Existing customers — route to account manager", ["existing_customer"])
show_group("➖ Unqualified — real people, low fit", ["unqualified"])
show_group("♻️ Duplicates — already in pipeline", ["duplicate"])
show_group("🚫 Spam — should not count as conversions", ["spam"])

# --- downloads --------------------------------------------------------------
st.markdown("### Export")
scored = []
for r in results:
    row = dict(r.raw)
    row["status"] = r.status
    row["quality_score"] = r.quality_score
    row["sales_ready"] = r.is_sales_ready
    row["reasons"] = " | ".join(r.reasons)
    scored.append(row)
scored_df = pd.DataFrame(scored)
csv_bytes = scored_df.to_csv(index=False).encode("utf-8")

d = st.columns(2)
d[0].download_button("⬇ Scored leads (CSV)", csv_bytes, file_name="scored_leads.csv", mime="text/csv")
d[1].download_button("⬇ Summary (JSON)", json.dumps(s, indent=2).encode(), file_name="summary.json",
                     mime="application/json")

st.markdown("---")
st.markdown(
    '<a class="cta" href="https://calendly.com/rajatdigiads/meetingrajat" target="_blank">Get a free audit</a>',
    unsafe_allow_html=True)
st.caption("Turquoise Digital · senior-led · month to month, no lock-in · no reporting theatre")

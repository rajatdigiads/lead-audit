# Lead-Quality Engine + Audit App (Build #1)

Classifies inbound Google Ads leads into **spam / duplicate / existing_customer / qualified / unqualified**, with an evidence trail for every decision. **No Google Ads API required** — it reads a lead export (form webhook, CRM, or CSV).

Two ways to run it: a **command-line** version and a **branded web app** (Streamlit).

## Files
- `lead_quality_engine.py` — the engine. All rules & thresholds live in `CONFIG`.
- `core_io.py` — shared CSV column auto-detection + row→lead mapping.
- `app.py` — **Streamlit audit app** (Turquoise-branded, drag-drop CSV).
- `load_csv.py` — command-line runner.
- `run_report.py` — builds the markdown report.
- `simulate_leads.py` — 17 labelled test leads.
- `test_engine.py` — 56 assertions → **56 passed, 0 failed**.
- `sample_real_leads.csv` — a realistic sample export to try.
- `requirements.txt`, `.streamlit/config.toml` — for the app.

---

## Option A — the web app (recommended for audits)

### Run it locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
A browser tab opens. In the sidebar set the client's **service area** suburbs/postcodes (and optionally paste known customers), then drag in a lead CSV. You get the "find the leak" headline, metric tiles, a breakdown chart, categorized lead tables with reasons, and CSV/JSON downloads.

### Deploy it free (so you can send a link / screen-share)
1. Put this folder in a GitHub repo.
2. Go to **share.streamlit.io** → New app → point at your repo → `app.py`.
3. It builds and gives you a public URL. (Keep client data out of the repo — upload CSVs at runtime only.)

## Option B — command line
```bash
python3 test_engine.py            # prove it works (56 passed)
python3 run_report.py             # demo report from simulated leads
python3 load_csv.py your.csv      # run on a real export -> report.md
```
First run with no file writes `client_config.json` — edit `service_area_terms` and `existing_customers`, then re-run.

---

## Accuracy lever
`service_area_terms` per client is the single biggest accuracy setting — it's what marks out-of-area leads as unqualified. Set it for every client.

## What's NOT here yet (next builds)
- Call-transcript scoring (Build A2)
- Offline conversion upload to Google Ads (Tier 3 — needs API)
- n8n live wiring (form → score → CRM/Slack)

## Rule design
Evidence-based: every spam/duplicate/existing result carries `reasons`; every score shows the exact +/− points. Nothing is invented.

# Turquoise — Lead & Customer Intelligence (v2)

One tool, **two profiles**. No Google Ads API required — reads a CSV export.

- **Trades / Local-service leads** — scores web-form leads: spam / duplicate / existing / qualified / unqualified, **plus lead-quality by campaign** (where to add negatives / shift budget).
- **Ecommerce / Customer list** — segments a customer DB by value (VIP / repeat / one-time / never-bought / junk), shows revenue concentration, region, B2B & list-health, and builds **Google Ads Customer Match** files.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
Pick the profile in the sidebar, set the client details, upload a CSV.

## Deploy (custom domain)
Push to a **private** GitHub repo → deploy on **Render** or **Railway** →
add `audit.yourdomain` as a custom domain (one CNAME record). Or free (no custom
domain) on share.streamlit.io.

Start command for Render/Railway:
`streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

## Files
- `app.py` — the two-mode web app (Turquoise branded).
- `lead_quality_engine.py` + `core_io.py` — trades lead engine.
- `customer_list.py` — ecommerce customer-list engine + Customer Match exports.
- `load_csv.py` / `run_report.py` — command-line trades runner.
- `test_engine.py` — 56 tests (trades engine).
- `sample_real_leads.csv` — sample for trades mode.

## Google Ads exports (ecommerce mode)
- **customer_match_high_value** — repeat+VIP buyers → value-based bidding seed + lookalikes.
- **customer_match_win_back** — one-time buyers → 2nd-purchase campaign.
- **exclusion_never_purchased** — signed-up-never-bought → exclude from prospecting.
Files use Google's Customer Match template columns; Google hashes on upload.

## Note
Validated on synthetic trades data + a real Shopify B2B export. Tune per client:
service-area (trades) and VIP threshold (ecommerce) are the main levers.

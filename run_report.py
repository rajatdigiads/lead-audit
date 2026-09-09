"""
Run the engine on the simulated batch and produce:
  1. A plain-text report (stdout)
  2. report.md  — client/agency-facing markdown
Evidence-based: every non-clean lead shows the exact reason it was flagged.
"""

from datetime import datetime

from lead_quality_engine import process_batch, summarize
from simulate_leads import get_leads_for_engine, CLIENT_CONFIG

STATUS_LABEL = {
    "spam": "SPAM",
    "duplicate": "DUPLICATE",
    "existing_customer": "EXISTING CUSTOMER",
    "qualified": "QUALIFIED",
    "unqualified": "UNQUALIFIED",
}


def build_report(results, s) -> str:
    L = []
    L.append("# Lead-Quality Report\n")
    L.append(f"Generated: {datetime.now():%Y-%m-%d}  ·  {s['total_leads']} leads in batch\n")
    L.append("## Headline\n")
    L.append(f"- **Lead Quality:** {s['lead_quality_pct']}%  "
             f"({s['real_leads']} real of {s['total_leads']} received)")
    L.append(f"- **Spam + Duplicate filtered out:** {s['spam_and_duplicate']} "
             f"({s['counts']['spam']} spam, {s['counts']['duplicate']} duplicate)")
    L.append(f"- **Existing customers (not new business):** {s['counts']['existing_customer']}")
    L.append(f"- **New-business leads:** {s['new_business_leads']}  →  "
             f"**{s['qualified']} qualified** / {s['counts']['unqualified']} unqualified")
    L.append(f"- **Qualified rate (of real leads):** {s['qualified_rate_pct']}%")
    L.append(f"- **Sales-ready (score ≥ 75):** {s['sales_ready']}\n")

    L.append(f"> Why this matters: you paid Google for **all {s['total_leads']} clicks**, but only "
             f"**{s['qualified']}** are jobs worth chasing. Optimising to raw lead "
             "volume would reward the campaigns sending spam and tyre-kickers.\n")

    def section(title, statuses):
        rows = [r for r in results if r.status in statuses]
        if not rows:
            return
        L.append(f"## {title} ({len(rows)})\n")
        for r in sorted(rows, key=lambda x: -x.quality_score):
            name = r.raw.get("name") or "(no name)"
            camp = r.raw.get("campaign", "—")
            score = f" · score {r.quality_score}" if r.status in ("qualified", "unqualified", "existing_customer") else ""
            sr = " · ⭐ SALES-READY" if r.is_sales_ready else ""
            L.append(f"**{r.lead_id} — {name}**  ({STATUS_LABEL[r.status]}{score}{sr})")
            L.append(f"  · Campaign: {camp}")
            for reason in r.reasons:
                L.append(f"  · {reason}")
            L.append("")

    section("✅ Qualified — chase these", ["qualified"])
    section("🔁 Existing customers — route to account manager", ["existing_customer"])
    section("➖ Unqualified — real people, low fit", ["unqualified"])
    section("♻️ Duplicates — already in your pipeline", ["duplicate"])
    section("🚫 Spam — do not count as conversions", ["spam"])
    return "\n".join(L)


def main():
    results = process_batch(get_leads_for_engine(), CLIENT_CONFIG)
    s = summarize(results)
    report = build_report(results, s)
    with open("report.md", "w") as f:
        f.write(report)
    print(report)
    print("\n[written] report.md")


if __name__ == "__main__":
    main()

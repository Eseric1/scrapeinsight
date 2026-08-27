"""Build a client-facing sample PDF report from a real ScrapeInsight run."""
import html
import json

import httpx

TARGET = "satechi"
OUT_HTML = r"C:\Users\erics\Downloads\scrapeinsight-report.html"


def run_analyze() -> dict:
    with httpx.stream(
        "POST", "http://127.0.0.1:8902/api/analyze", json={"target": TARGET}, timeout=300
    ) as r:
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                lines = raw.split("\n")
                ev = next((ln[7:] for ln in lines if ln.startswith("event: ")), "")
                data = next((ln[6:] for ln in lines if ln.startswith("data: ")), "")
                if ev == "result":
                    return json.loads(data)
                if ev == "error":
                    raise SystemExit(f"analyze error: {data}")
    raise SystemExit("no result event")


def fmt_price(v):
    return "—" if v is None else f"${v:,.2f}"


d = run_analyze()
stats = d["stats"]
price = stats["numeric"].get("price", {})

rows = "\n".join(
    f"<tr><td>{html.escape(r['name'])}</td><td class='num'>{fmt_price(r['price'])}</td></tr>"
    for r in d["records"]
)
insights = "\n".join(
    f"<li>{html.escape(i)}</li>" for i in d["insights"]
)

page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1c1e21; margin: 48px 56px; }}
  .brand {{ font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }}
  .brand span {{ color: #e8541d; }}
  .sub {{ color: #666; font-size: 12px; margin-top: 4px; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: 1px; color: #e8541d;
       border-bottom: 2px solid #eee; padding-bottom: 6px; margin-top: 34px; }}
  .meta {{ background: #faf8f4; border: 1px solid #e5e0d5; border-radius: 8px;
           padding: 14px 18px; margin-top: 22px; font-size: 13px; line-height: 1.7; }}
  .tiles {{ display: flex; gap: 14px; margin-top: 10px; }}
  .tile {{ flex: 1; border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; }}
  .tile .v {{ font-size: 22px; font-weight: 800; }}
  .tile .l {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #888; }}
  ul {{ line-height: 1.8; font-size: 13.5px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }}
  th {{ text-align: left; border-bottom: 2px solid #333; padding: 6px 8px;
       text-transform: uppercase; font-size: 10px; letter-spacing: 1px; }}
  td {{ border-bottom: 1px solid #eee; padding: 6px 8px; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .foot {{ margin-top: 40px; font-size: 11px; color: #999; border-top: 1px solid #eee; padding-top: 10px; }}
</style></head><body>
  <div class="brand">Scrape<span>Insight</span> — Sample Data Extract &amp; Insights Report</div>
  <div class="sub">Prepared as a service sample · what every delivery includes</div>

  <div class="meta">
    <b>Source:</b> {html.escape(d['source']['label'])} ({html.escape(d['source']['url'])})<br>
    <b>Pulled:</b> {html.escape(d['fetched_at'])} · live at run time, nothing cached<br>
    <b>Extraction:</b> deterministic structured-data parsing (schema.org / product feeds), AI fallback for unstructured pages<br>
    <b>Records:</b> {d['total_found']} products extracted
  </div>

  <h2>Key numbers</h2>
  <div class="tiles">
    <div class="tile"><div class="v">{stats['row_count']}</div><div class="l">Products</div></div>
    <div class="tile"><div class="v">{fmt_price(price.get('mean'))}</div><div class="l">Mean price</div></div>
    <div class="tile"><div class="v">{fmt_price(price.get('median'))}</div><div class="l">Median price</div></div>
    <div class="tile"><div class="v">{fmt_price(price.get('min'))} – {fmt_price(price.get('max'))}</div><div class="l">Range</div></div>
  </div>

  <h2>What the numbers say</h2>
  <ul>{insights}</ul>
  <p style="font-size:11.5px;color:#888">Every figure above is computed in code from the extracted
  records — the AI writes the narrative but never invents a number.</p>

  <h2>Extracted records (sample)</h2>
  <table><tr><th>Product</th><th class="num">Price</th></tr>{rows}</table>

  <div class="foot">Deliverables include the full record set as CSV/Excel, this report as PDF,
  and (per tier) an interactive dashboard and re-runnable pipeline with source code.
  Public, scrape-permissible sites only.</div>
</body></html>"""

open(OUT_HTML, "w", encoding="utf-8").write(page)
print("report html written:", OUT_HTML, "| records:", d["total_found"])

"""Deterministic statistics — the numbers the model's insight bullets must cite.

Everything mechanical (counts, means, distributions) is computed in pandas;
the LLM only narrates numbers that already exist here.
"""
import pandas as pd


def analyze(records: list[dict], preset: dict) -> dict:
    df = pd.DataFrame(records)
    result: dict = {"row_count": len(df), "numeric": {}, "categories": {}, "charts": []}
    if df.empty:
        return result

    for col in preset["numeric"]:
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            continue
        result["numeric"][col] = {
            "count": int(s.count()),
            "mean": round(float(s.mean()), 2),
            "median": round(float(s.median()), 2),
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
        }
        if s.nunique() > 1 and len(s) >= 5:
            bins = min(8, max(3, int(s.nunique())))
            counts = pd.cut(s, bins=bins).value_counts().sort_index()
            result["charts"].append(
                {
                    "id": f"hist-{col}",
                    "type": "bar",
                    "title": f"{col} distribution",
                    "labels": [f"{iv.left:g}–{iv.right:g}" for iv in counts.index],
                    "values": [int(v) for v in counts],
                }
            )

    for col in preset["categorical"]:
        if col not in df:
            continue
        s = df[col].dropna().astype(str).str.strip()
        s = s[s != ""]
        if s.empty or s.nunique() < 2:
            continue
        top = s.value_counts().head(8)
        result["categories"][col] = {str(k): int(v) for k, v in top.items()}
        result["charts"].append(
            {
                "id": f"top-{col}",
                "type": "bar",
                "horizontal": True,
                "title": f"{col} breakdown",
                "labels": [str(k) for k in top.index],
                "values": [int(v) for v in top],
            }
        )

    nums = [c for c in preset["numeric"] if c in result["numeric"]]
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        pair = df[[a, b]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) >= 5:
            result["charts"].append(
                {
                    "id": f"scatter-{a}-{b}",
                    "type": "scatter",
                    "title": f"{a} vs {b}",
                    "x_label": a,
                    "y_label": b,
                    "points": [
                        {"x": float(row[a]), "y": float(row[b])}
                        for _, row in pair.head(200).iterrows()
                    ],
                }
            )
    return result

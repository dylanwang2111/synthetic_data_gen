"""
Render reports/quality_report.png — the SDMetrics QualityReport breakdown
(overall quality + its sub-scores) across all 5 methods, as grouped bars.
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.metrics_extended import _sdmetrics_scores

METHODS = {"M1 HMA-GC": "m1", "M2 CTGAN": "m2", "M3 PAR": "m3",
           "M4 TVAE": "m4", "M5 MST-DP": "m5"}

real = {"customers": pd.read_csv("data/real_customers.csv"),
        "transactions": pd.read_csv("data/real_transactions.csv")}

rows = []
for name, p in METHODS.items():
    syn = {"customers": pd.read_csv(f"data/{p}_customers.csv"),
           "transactions": pd.read_csv(f"data/{p}_transactions.csv")}
    s = _sdmetrics_scores(real, syn)
    rows.append({"method": name, **s})
df = pd.DataFrame(rows).set_index("method")
df.to_csv("reports/quality_report.csv")
print(df.round(3))

# Grouped bars: x = method, 4 bars (Overall, Cust shapes, Cust pairs, Txn shapes)
metrics = [("quality_score", "Overall quality", "#1F2A37"),
           ("cust_column_shapes", "Cust. column shapes", "#4E79A7"),
           ("cust_pair_trends", "Cust. pair trends", "#59A14F"),
           ("txn_column_shapes", "Txn. column shapes", "#F28E2B")]

methods = list(df.index)
x = np.arange(len(methods))
w = 0.2
fig, ax = plt.subplots(figsize=(12, 5.6))
for k, (col, label, color) in enumerate(metrics):
    vals = df[col].values
    bars = ax.bar(x + (k - 1.5) * w, vals, w, label=label, color=color)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.2f}",
                ha="center", va="bottom", fontsize=8.5, color="#333")

ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=11)
ax.set_ylim(0, 1.08)
ax.set_ylabel("Score  (higher = better)", fontsize=11)
ax.set_title("SDMetrics Quality Report — overall score and its sub-components",
             fontsize=14, fontweight="bold")
ax.legend(ncol=4, fontsize=10, loc="upper center", bbox_to_anchor=(0.5, -0.08),
          frameon=False)
ax.grid(axis="y", alpha=0.3)
ax.axhline(df["quality_score"].max(), ls="--", lw=0.8, color="#999", alpha=0.6)
fig.tight_layout()
fig.savefig("reports/quality_report.png", dpi=140, bbox_inches="tight")
print("wrote reports/quality_report.png")

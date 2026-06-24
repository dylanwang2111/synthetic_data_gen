"""
Build the headline SDV-vs-SmartNoise comparison: mean ± SD per metric across
fidelity, diagnostic (referential integrity), and privacy.

SDV is represented by M1 (HMA-GC, the recommended multi-table method);
SmartNoise is M5 (MST, differential privacy).

Outputs
-------
reports/sdv_vs_smartnoise.csv   mean ± SD per metric for both paradigms
reports/sdv_vs_smartnoise.png   grouped bars (mean) with ±SD error bars
"""

import os, sys
# allow running from anywhere: put repo root on the path and use it as cwd
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT); os.chdir(_ROOT)


import random
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.seed_data import make_seed_data
from src.metrics_extended import bootstrap_privacy_audit

SDV, DP = "M1 HMA-GC", "M5 MST-DP"
SDV_C, DP_C = "#4E79A7", "#B07AA1"

# ── fidelity + diagnostic: mean ± SD from the metric bootstrap (B=200) ────────
raw = pd.read_csv("reports/bootstrap_raw.csv")
g = raw.groupby("method")

# ── privacy: MIA AUC mean ± SD from the audit bootstrap (B=300) ───────────────
real = pd.read_csv("data/real_customers.csv")
random.seed(2024); np.random.seed(2024)
nonmembers = make_seed_data(n_customers=len(real))["customers"]
syn = {m: {"customers": pd.read_csv(f"data/{p}_customers.csv")}
       for m, p in {SDV: "m1", DP: "m5"}.items()}
audit_raw = bootstrap_privacy_audit(real, nonmembers, syn, n_boot=300, seed=0)["raw"]
ag = audit_raw.groupby("method")

# metric label, column source, group
METRICS = [
    ("Quality\n(fidelity)",      "quality_score",      g),
    ("Cust. column\nshapes",     "cust_column_shapes", g),
    ("Cust. pair\ntrends",       "cust_pair_trends",   g),
    ("Txn. column\nshapes",      "txn_column_shapes",  g),
    ("Diagnostic\n(ref. integ.)","diagnostic_score",   g),
    ("Privacy\n(MIA AUC)",       "mia_auc",            ag),
]

rows = []
for label, col, grp in METRICS:
    rows.append({
        "metric": label.replace("\n", " "),
        "sdv_mean": grp.get_group(SDV)[col].mean(),
        "sdv_sd":   grp.get_group(SDV)[col].std(),
        "dp_mean":  grp.get_group(DP)[col].mean(),
        "dp_sd":    grp.get_group(DP)[col].std(),
    })
tbl = pd.DataFrame(rows).set_index("metric")
tbl.to_csv("reports/sdv_vs_smartnoise.csv")
print(tbl.round(4).to_string())

# ── chart: grouped bars (mean) with ±SD error bars ───────────────────────────
labels = [m[0] for m in METRICS]
x = np.arange(len(labels)); w = 0.38
fig, ax = plt.subplots(figsize=(12.5, 5.6))
ax.bar(x - w/2, tbl["sdv_mean"], w, yerr=tbl["sdv_sd"], capsize=4, color=SDV_C,
       label="SDV  (M1 HMA-GC)", error_kw=dict(ecolor="#22303c", lw=1.4))
ax.bar(x + w/2, tbl["dp_mean"], w, yerr=tbl["dp_sd"], capsize=4, color=DP_C,
       label="SmartNoise  (M5 MST, DP)", error_kw=dict(ecolor="#22303c", lw=1.4))
for xi, (_, r) in zip(x, tbl.iterrows()):
    ax.text(xi - w/2, r["sdv_mean"] + r["sdv_sd"] + 0.015, f"{r['sdv_mean']:.2f}\n±{r['sdv_sd']:.3f}",
            ha="center", va="bottom", fontsize=8.5, color=SDV_C)
    ax.text(xi + w/2, r["dp_mean"] + r["dp_sd"] + 0.015, f"{r['dp_mean']:.2f}\n±{r['dp_sd']:.3f}",
            ha="center", va="bottom", fontsize=8.5, color=DP_C)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
ax.set_ylim(0, 1.18); ax.set_ylabel("Score  (mean ± SD, higher = better)", fontsize=11)
ax.axhline(0.5, ls=":", color="#999", lw=1)
ax.legend(fontsize=11, loc="upper right", frameon=False)
ax.set_title("SDV vs SmartNoise — mean ± variance per metric (bootstrap)",
             fontsize=14, fontweight="bold")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("reports/sdv_vs_smartnoise.png", dpi=140, bbox_inches="tight")
print("wrote reports/sdv_vs_smartnoise.png")

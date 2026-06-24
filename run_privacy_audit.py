"""
Measurable privacy: distance-based membership-inference audit across all methods.

Members      = the real training customers (data/real_customers.csv).
Non-members  = a fresh draw from the SAME generative process (different seed),
               never seen by any synthesizer — the control group.

Outputs
-------
reports/privacy_audit.csv   MIA AUC, advantage, empirical-eps lower bound per method
reports/privacy_audit.png   AUC and empirical-eps bars (with the 0.5 / ε≈6 references)
"""

import random
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.seed_data import make_seed_data
from src.metrics_extended import compare_privacy_audit, bootstrap_privacy_audit

N_BOOT = 300
METHODS = {"M1 HMA-GC": "m1", "M2 CTGAN": "m2", "M3 PAR": "m3",
           "M4 TVAE": "m4", "M5 MST-DP": "m5"}
COLOR = {"M1 HMA-GC": "#4E79A7", "M2 CTGAN": "#F28E2B", "M3 PAR": "#59A14F",
         "M4 TVAE": "#E15759", "M5 MST-DP": "#B07AA1"}
M5_BUDGET = 6.0   # configured (ε≈3/table × 2)

real = pd.read_csv("data/real_customers.csv")

# Fresh, disjoint non-member control from the same generative process.
random.seed(2024); np.random.seed(2024)
nonmembers = make_seed_data(n_customers=len(real))["customers"]

syn = {name: {"customers": pd.read_csv(f"data/{p}_customers.csv")}
       for name, p in METHODS.items()}

# Point estimates + bootstrap 95% CIs.
df = compare_privacy_audit(real, nonmembers, syn).reindex(list(METHODS))
df.to_csv("reports/privacy_audit.csv")
boot = bootstrap_privacy_audit(real, nonmembers, syn, n_boot=N_BOOT, seed=0)
summ = boot["summary"].reindex(list(METHODS))
summ.to_csv("reports/privacy_audit_boot.csv")
print(df.round(4)); print(summ.round(4))


def err(metric):
    """asymmetric [low, high] error-bar offsets from the bootstrap summary."""
    med = summ[f"{metric}_median"].values
    lo  = med - summ[f"{metric}_ci_low"].values
    hi  = summ[f"{metric}_ci_high"].values - med
    return med, np.vstack([lo, hi])


methods = list(df.index)
colors = [COLOR[m] for m in methods]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.2))

auc_med, auc_err = err("mia_auc")
b1 = a1.bar(methods, auc_med, color=colors, yerr=auc_err, capsize=5,
            error_kw=dict(ecolor="#333", lw=1.3))
a1.axhline(0.5, ls="--", color="#888", lw=1.2)
a1.text(len(methods) - 0.5, 0.503, "0.5 = no leakage", ha="right", fontsize=9, color="#666")
a1.set_ylim(0.45, max(0.62, summ["mia_auc_ci_high"].max() + 0.03))
a1.set_title("Membership-inference AUC  (↓ = more private)", fontsize=12, fontweight="bold")
for b, v in zip(b1, auc_med):
    a1.text(b.get_x() + b.get_width() / 2, 0.458, f"{v:.3f}", ha="center", fontsize=9.5)

eps_pt = df["eps_lower"].values   # Clopper-Pearson 95% bound (already a confidence bound)
b2 = a2.bar(methods, eps_pt, color=colors)
a2.axhline(M5_BUDGET, ls="--", color=COLOR["M5 MST-DP"], lw=1.4)
a2.text(len(methods) - 0.5, M5_BUDGET + 0.12, "M5 budget ε≈6", ha="right",
        fontsize=9, color=COLOR["M5 MST-DP"])
a2.set_ylim(0, M5_BUDGET + 0.8)
a2.set_title("Empirical ε lower bound — Clopper-Pearson 95%  (↓ = more private)",
             fontsize=11.5, fontweight="bold")
for b, v in zip(b2, eps_pt):
    a2.text(b.get_x() + b.get_width() / 2, v + 0.12, f"{v:.2f}", ha="center", fontsize=9.5)

for ax in (a1, a2):
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="x", labelsize=10)
fig.suptitle(f"Measured privacy — membership-inference audit (95% bootstrap CIs, B={N_BOOT})",
             fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig("reports/privacy_audit.png", dpi=140, bbox_inches="tight")
print("wrote reports/privacy_audit.png")

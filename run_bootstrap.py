"""
Bootstrap the full 5-method metrics comparison and write results to reports/.

Outputs
-------
reports/bootstrap_raw.csv        one row per (method, iteration), all metrics
reports/bootstrap_summary.csv    median + 95% CI per method per metric
reports/bootstrap_ci_table.csv   'median [low, high]' strings (presentation)
reports/bootstrap_ci.png         forest plot of key metrics with 95% CIs
"""

import time
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.metrics_extended import bootstrap_compare_methods, format_ci_table

N_BOOT = 200
N_BOOT_PRIV = 40
PRIV_SUBSAMPLE = 500

METHODS = {
    "M1 HMA-GC":  "m1",
    "M2 CTGAN":   "m2",
    "M3 PAR":     "m3",
    "M4 TVAE":    "m4",
    "M5 MST-DP":  "m5",
}

METHOD_COLOR = {
    "M1 HMA-GC": "#4C72B0", "M2 CTGAN": "#DD8452", "M3 PAR": "#55A868",
    "M4 TVAE": "#C44E52", "M5 MST-DP": "#8172B3",
}


def load():
    real = {"customers": pd.read_csv("data/real_customers.csv"),
            "transactions": pd.read_csv("data/real_transactions.csv")}
    syn = {name: {"customers": pd.read_csv(f"data/{p}_customers.csv"),
                  "transactions": pd.read_csv(f"data/{p}_transactions.csv")}
           for name, p in METHODS.items()}
    return real, syn


# Metrics to plot: (column, pretty label, higher_is_better)
PLOT_METRICS = [
    ("quality_score",   "Quality (SDMetrics)",   True),
    ("cust_pair_trends","Cust. pair trends",     True),
    ("txn_column_shapes","Txn column shapes",    True),
    ("cross_table_mad", "Cross-table MAD",        False),
    ("autocorr_mae",    "Autocorr MAE",           False),
    ("dcr_protection",  "DCR protection",         True),
]


def forest_plot(summary: pd.DataFrame, path: str):
    methods = list(summary.index)
    n = len(PLOT_METRICS)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.ravel()
    for ax, (col, label, higher) in zip(axes, PLOT_METRICS):
        med, lo, hi = f"{col}_median", f"{col}_ci_low", f"{col}_ci_high"
        if med not in summary.columns:
            ax.set_visible(False)
            continue
        ys = range(len(methods))
        for y, m in zip(ys, methods):
            c = METHOD_COLOR.get(m, "#333")
            center = summary.loc[m, med]
            left = center - summary.loc[m, lo]
            right = summary.loc[m, hi] - center
            ax.errorbar(center, y, xerr=[[left], [right]], fmt="o",
                        color=c, ecolor=c, elinewidth=2, capsize=4, markersize=7)
        ax.set_yticks(list(ys))
        ax.set_yticklabels(methods, fontsize=9)
        ax.invert_yaxis()
        arrow = "↑ better" if higher else "↓ better"
        ax.set_title(f"{label}  ({arrow})", fontsize=11, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
    fig.suptitle(f"Metric comparison with 95% bootstrap CIs  (B={N_BOOT}, "
                 f"privacy B={N_BOOT_PRIV})", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=130, bbox_inches="tight")
    print(f"  wrote {path}")


def main():
    t0 = time.time()
    real, syn = load()
    print(f"Loaded real ({len(real['customers'])} cust) + {len(syn)} methods")
    res = bootstrap_compare_methods(
        real, syn, n_boot=N_BOOT, n_boot_privacy=N_BOOT_PRIV,
        priv_subsample=PRIV_SUBSAMPLE, seed=0, progress_every=10)

    raw, summary = res["raw"], res["summary"]
    raw.to_csv("reports/bootstrap_raw.csv", index=False)
    summary.to_csv("reports/bootstrap_summary.csv")
    ci_table = format_ci_table(summary)
    ci_table.to_csv("reports/bootstrap_ci_table.csv")
    forest_plot(summary, "reports/bootstrap_ci.png")

    print("\n=== Bootstrap CI table (median [2.5%, 97.5%]) ===")
    print(ci_table.T.to_string())
    print(f"\nDone in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()

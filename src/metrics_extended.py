"""
Extended evaluation metrics beyond SDMetrics' standard reports.

cross_table_correlation  – Spearman correlation between customer features
                           (income, credit_score, age) and per-customer
                           product-category mix.  Measures whether the
                           income→investment-product relationship is preserved.

temporal_stats           – Inter-arrival time distribution + amount
                           autocorrelation (lag-1).  Measures whether
                           transaction sequences are temporally realistic.

compare_methods          – Runs all metrics across multiple synthetic datasets
                           and returns a tidy comparison DataFrame.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ks_2samp
from sdmetrics.reports.multi_table import QualityReport, DiagnosticReport
from sdmetrics.single_table import NewRowSynthesis, DCRBaselineProtection

from .schema import build_metadata_2table

FEATURE_COLS   = ["income", "credit_score", "age"]
CATEGORY_COLS  = ["Banking", "Credit", "Insurance", "Investment"]


# ─────────────────────────────────────────────────────────────────────────────
# Cross-table correlation
# ─────────────────────────────────────────────────────────────────────────────

def _customer_category_pcts(customers: pd.DataFrame,
                             transactions: pd.DataFrame) -> pd.DataFrame:
    cat = (transactions.groupby(["customer_id", "product_category"])
                       .size().unstack(fill_value=0))
    for col in CATEGORY_COLS:
        if col not in cat.columns:
            cat[col] = 0
    cat = cat[CATEGORY_COLS]
    cat_pct = cat.div(cat.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    return customers.set_index("customer_id")[FEATURE_COLS].join(cat_pct, how="inner")


def cross_table_correlation(customers: pd.DataFrame,
                             transactions: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation matrix: features × product categories."""
    merged = _customer_category_pcts(customers, transactions)
    rows = []
    for feat in FEATURE_COLS:
        for cat in CATEGORY_COLS:
            corr, pval = spearmanr(merged[feat], merged[cat])
            rows.append({"feature": feat, "category": cat,
                         "spearman_r": round(corr, 4), "p_value": round(pval, 4)})
    return pd.DataFrame(rows)


def cross_table_score(real_customers, real_transactions,
                      syn_customers, syn_transactions) -> dict:
    """
    Mean absolute difference of Spearman correlations between real and synthetic.
    Lower = better.  Also returns the per-pair delta for inspection.
    """
    real_corr = cross_table_correlation(real_customers, real_transactions)
    syn_corr  = cross_table_correlation(syn_customers,  syn_transactions)
    merged    = real_corr.merge(syn_corr, on=["feature","category"],
                                suffixes=("_real","_syn"))
    merged["delta"] = (merged["spearman_r_real"] - merged["spearman_r_syn"]).abs()
    return {
        "mean_abs_delta": round(merged["delta"].mean(), 4),
        "max_abs_delta":  round(merged["delta"].max(),  4),
        "detail":         merged,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Temporal realism
# ─────────────────────────────────────────────────────────────────────────────

def temporal_stats(transactions: pd.DataFrame) -> dict:
    """
    Inter-arrival times (days) and amount autocorrelation per customer.
    Requires transaction_date column parseable as datetime.
    """
    df = transactions.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df = df.sort_values(["customer_id", "transaction_date"])
    df["prev_date"] = df.groupby("customer_id")["transaction_date"].shift(1)
    df["inter_arrival"] = (df["transaction_date"] - df["prev_date"]).dt.days
    ia = df["inter_arrival"].dropna()

    # Per-customer lag-1 autocorrelation of amounts
    def _autocorr(x):
        return x.autocorr(lag=1) if len(x) > 2 else np.nan

    autocorr_vals = (df.groupby("customer_id")["amount"]
                       .apply(_autocorr)
                       .dropna())

    return {
        "inter_arrival_mean":   round(float(ia.mean()),   2),
        "inter_arrival_median": round(float(ia.median()), 2),
        "inter_arrival_std":    round(float(ia.std()),    2),
        "amount_autocorr_mean": round(float(autocorr_vals.mean()), 4),
        "inter_arrival_values": ia.values,        # kept for KS test
        "autocorr_values":      autocorr_vals.values,
    }


def temporal_score(real_transactions: pd.DataFrame,
                   syn_transactions:  pd.DataFrame) -> dict:
    """
    KS test on inter-arrival distribution + autocorrelation MAE.
    Higher KS p-value = more similar distributions (better).
    Lower autocorr_mae = better.
    """
    real_stats = temporal_stats(real_transactions)
    syn_stats  = temporal_stats(syn_transactions)

    ks_stat, ks_pval = ks_2samp(real_stats["inter_arrival_values"],
                                  syn_stats["inter_arrival_values"])
    autocorr_mae = abs(real_stats["amount_autocorr_mean"] -
                       syn_stats["amount_autocorr_mean"])

    return {
        "ia_ks_statistic":  round(ks_stat,      4),
        "ia_ks_pvalue":     round(ks_pval,      4),   # higher = more similar
        "autocorr_mae":     round(autocorr_mae, 4),   # lower  = better
        "syn_ia_mean":      syn_stats["inter_arrival_mean"],
        "syn_ia_median":    syn_stats["inter_arrival_median"],
        "syn_ia_std":       syn_stats["inter_arrival_std"],
        "syn_autocorr":     syn_stats["amount_autocorr_mean"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Standard SDMetrics quality / diagnostic
# ─────────────────────────────────────────────────────────────────────────────

def _sdmetrics_scores(real_data: dict, syn_data: dict) -> dict:
    meta = build_metadata_2table()
    meta_dict = meta.to_dict()

    q = QualityReport()
    q.generate(real_data, syn_data, meta_dict, verbose=False)
    q_score = q.get_score()

    d = DiagnosticReport()
    d.generate(real_data, syn_data, meta_dict, verbose=False)
    d_score = d.get_score()

    shapes = q.get_details("Column Shapes")
    pairs  = q.get_details("Column Pair Trends")

    cust_shapes = shapes.loc[shapes["Table"] == "customers", "Score"].mean()
    cust_pairs  = pairs.loc[pairs["Table"]  == "customers", "Score"].mean()
    txn_shapes  = shapes.loc[shapes["Table"] == "transactions", "Score"].mean()

    return {
        "quality_score":        round(q_score, 4),
        "diagnostic_score":     round(d_score, 4),
        "cust_column_shapes":   round(float(cust_shapes), 4),
        "cust_pair_trends":     round(float(cust_pairs),  4),
        "txn_column_shapes":    round(float(txn_shapes),  4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Compare all methods
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Empirical privacy (SDMetrics)
# ─────────────────────────────────────────────────────────────────────────────

def _customers_single_meta() -> dict:
    """Single-table metadata for the customers table, excluding the id column."""
    cols = build_metadata_2table().to_dict()["tables"]["customers"]["columns"]
    return {"columns": {k: v for k, v in cols.items() if k != "customer_id"}}


def privacy_scores(real_customers: pd.DataFrame, syn_customers: pd.DataFrame,
                   subsample: int = 1000) -> dict:
    """
    Empirical privacy of the (PII-bearing) customers table. Both metrics: higher = more private.

    new_row_synthesis : fraction of synthetic rows that are NOT copies of a real row
                        (verbatim within a numerical tolerance).
    dcr_protection    : DCRBaselineProtection — synthetic→real distance-to-closest-record
                        vs a random-data baseline; low values flag memorisation.
    """
    meta = _customers_single_meta()
    r = real_customers.drop(columns=["customer_id"])
    s = syn_customers.drop(columns=["customer_id"])
    n_sample = min(len(s), subsample)
    new_row = NewRowSynthesis.compute(r, s, meta, synthetic_sample_size=n_sample)
    dcr     = DCRBaselineProtection.compute(r, s, meta, num_rows_subsample=subsample)
    return {"new_row_synthesis": round(float(new_row), 4),
            "dcr_protection":    round(float(dcr), 4)}


# ─────────────────────────────────────────────────────────────────────────────
# Measurable privacy: distance-based membership-inference audit
# ─────────────────────────────────────────────────────────────────────────────
#
# ε itself is *accounted*, not measured — it is a worst-case property of the
# algorithm.  What we CAN measure empirically (for every method, DP or not) is
# how much the synthetic output leaks membership: can an attacker tell whether a
# record was in the training set?
#
# Attack (DCR / DOMIAS-style): members = the real training customers; an
# independent "non-member" control is drawn from the SAME generative process but
# never seen by the synthesizer.  For each record we take the distance to its
# nearest synthetic row.  If the synthesizer memorises, members sit closer than
# non-members → the attacker (score = −distance) separates them → AUC > 0.5.
# The ROC is then converted to an empirical ε *lower bound* (Kairouz et al.).

CUST_NUM = ["age", "income", "credit_score", "tenure_years", "num_dependents"]
CUST_CAT = ["gender", "education", "occupation", "marital_status", "region", "is_churned"]


def _encode_customers(frames, ref, num_cols, cat_cols):
    """Mixed-type → numeric matrix: z-scored numerics + weighted one-hot cats.
    Scaling/categories are fixed from `ref` (the members) so all frames share a space."""
    mu = ref[num_cols].mean()
    sd = ref[num_cols].std().replace(0, 1.0)
    cats = {c: sorted(ref[c].astype(str).unique()) for c in cat_cols}
    out = []
    for df in frames:
        parts = [((df[num_cols] - mu) / sd).to_numpy(dtype=float)]
        for c in cat_cols:
            d = pd.get_dummies(df[c].astype(str)).reindex(columns=cats[c], fill_value=0)
            parts.append(d.to_numpy(dtype=float) * 0.7071)  # cat mismatch ≈ unit dist
        out.append(np.hstack(parts))
    return out


def _empirical_eps(dm: np.ndarray, dn: np.ndarray,
                   alpha: float = 0.05, delta: float = 1e-5) -> float:
    """Clopper-Pearson empirical ε lower bound (DP auditing, Jagielski/Nasr style).

    The attack flags a record as a member when its nearest-synthetic distance is
    below a threshold. Sweeping thresholds over the member-like (small-distance)
    region, we take a *confidence* lower bound on TPR and upper bound on FPR
    (Clopper-Pearson at level alpha) so a single noisy ROC corner cannot inflate
    the estimate, then ε = max_t log((TPR_lo − δ) / FPR_hi). Returns 0 when the
    attack is no better than chance — the honest answer for ~0.5 AUC."""
    from scipy.stats import beta
    n_pos, n_neg = len(dm), len(dn)
    # thresholds focused on the small-distance (member-flagging) region
    pool = np.concatenate([dm, dn])
    thr = np.quantile(pool, np.linspace(0.0, 0.5, 200))
    tp = (dm[:, None] <= thr[None, :]).sum(0)
    fp = (dn[:, None] <= thr[None, :]).sum(0)
    tpr_lo = np.where(tp > 0, beta.ppf(alpha / 2, tp, n_pos - tp + 1), 0.0)
    fpr_hi = np.where(fp < n_neg, beta.ppf(1 - alpha / 2, fp + 1, n_neg - fp), 1.0)
    fpr_hi = np.clip(fpr_hi, 1e-12, None)
    eps = np.log(np.clip((tpr_lo - delta) / fpr_hi, 1e-12, None))
    return max(0.0, float(np.nanmax(eps)))


def _audit_distances(members: pd.DataFrame, nonmembers: pd.DataFrame,
                     syn_customers: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-synthetic-record distance for each member and non-member.
    This is the expensive part (encode + NN fit); compute once, reuse for bootstrap."""
    from sklearn.neighbors import NearestNeighbors
    cols = lambda df: df[CUST_NUM + CUST_CAT]
    Xs, Xm, Xn = _encode_customers(
        [cols(syn_customers), cols(members), cols(nonmembers)],
        ref=members, num_cols=CUST_NUM, cat_cols=CUST_CAT)
    nn = NearestNeighbors(n_neighbors=1).fit(Xs)
    return nn.kneighbors(Xm)[0].ravel(), nn.kneighbors(Xn)[0].ravel()


def _auc_from_distances(dm: np.ndarray, dn: np.ndarray) -> float:
    """Attack AUC from member/non-member distance arrays (the fast, stable stat)."""
    from sklearn.metrics import roc_auc_score
    scores = np.concatenate([-dm, -dn])          # higher = more "member-like"
    labels = np.concatenate([np.ones_like(dm), np.zeros_like(dn)])
    return float(roc_auc_score(labels, scores))


def privacy_audit(members: pd.DataFrame, nonmembers: pd.DataFrame,
                  syn_customers: pd.DataFrame, delta: float = 1e-5) -> dict:
    """Distance-based membership-inference audit on the customers table.

    Returns:
      mia_auc        : attacker AUC (0.5 = no leakage, 1.0 = full membership leak)
      mia_advantage  : 2·AUC − 1  (0 = none)
      eps_lower      : Clopper-Pearson empirical ε lower bound (0 = no certifiable leak)
      member_dcr / nonmember_dcr : median nearest-synthetic distance for each group
    """
    dm, dn = _audit_distances(members, nonmembers, syn_customers)
    auc = _auc_from_distances(dm, dn)
    return {"mia_auc":       round(auc, 4),
            "mia_advantage": round(2 * auc - 1, 4),
            "eps_lower":     round(_empirical_eps(dm, dn, delta=delta), 4),
            "member_dcr":    round(float(np.median(dm)), 4),
            "nonmember_dcr": round(float(np.median(dn)), 4)}


def bootstrap_privacy_audit(real_customers: pd.DataFrame,
                            nonmember_customers: pd.DataFrame,
                            synthetic_datasets: dict[str, dict],
                            n_boot: int = 300, seed: int = 0,
                            delta: float = 1e-5) -> dict:
    """Bootstrap the membership-inference audit per method.

    The encode + nearest-neighbour step runs once per method; each bootstrap
    iteration only resamples the precomputed member / non-member distance arrays
    (with replacement) and recomputes AUC + empirical ε — so B can be large and
    cheap. Returns {"raw": long DataFrame, "summary": median + 95% CI per metric}.
    """
    rng = np.random.default_rng(seed)
    metrics = ["mia_auc", "mia_advantage"]
    rows = []
    for name, syn in synthetic_datasets.items():
        print(f"  Audit bootstrap: {name} …", flush=True)
        dm, dn = _audit_distances(real_customers, nonmember_customers, syn["customers"])
        nm, nn_ = len(dm), len(dn)
        for b in range(n_boot):
            dm_b = dm[rng.integers(0, nm, nm)]
            dn_b = dn[rng.integers(0, nn_, nn_)]
            auc = _auc_from_distances(dm_b, dn_b)
            rows.append({"method": name, "iter": b,
                         "mia_auc": auc, "mia_advantage": 2 * auc - 1})

    raw = pd.DataFrame(rows)
    summary_rows = []
    for name, g in raw.groupby("method", sort=False):
        rec = {"method": name}
        for m in metrics:
            ci = _ci(g[m])
            rec[f"{m}_median"]  = ci["median"]
            rec[f"{m}_ci_low"]  = ci["ci_low"]
            rec[f"{m}_ci_high"] = ci["ci_high"]
        summary_rows.append(rec)
    summary = pd.DataFrame(summary_rows).set_index("method")
    return {"raw": raw, "summary": summary}


def compare_privacy_audit(real_customers: pd.DataFrame,
                          nonmember_customers: pd.DataFrame,
                          synthetic_datasets: dict[str, dict]) -> pd.DataFrame:
    """Membership-inference audit across methods. Lower AUC / eps_lower = more private."""
    rows = []
    for name, syn in synthetic_datasets.items():
        print(f"  Audit: {name} …")
        row = {"method": name}
        try:
            row.update(privacy_audit(real_customers, nonmember_customers, syn["customers"]))
        except Exception as e:
            print(f"    ⚠ Audit error: {e}")
        rows.append(row)
    return pd.DataFrame(rows).set_index("method")


def compare_privacy(real_data: dict,
                    synthetic_datasets: dict[str, dict]) -> pd.DataFrame:
    """Privacy scorecard (customers table) across methods. Higher = more private."""
    rows = []
    for name, syn in synthetic_datasets.items():
        print(f"  Privacy: {name} …")
        row = {"method": name}
        try:
            row.update(privacy_scores(real_data["customers"], syn["customers"]))
        except Exception as e:
            print(f"    ⚠ Privacy error: {e}")
        rows.append(row)
    return pd.DataFrame(rows).set_index("method")


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap confidence intervals
# ─────────────────────────────────────────────────────────────────────────────
#
# Every metric above is a *point estimate* computed from one finite real sample
# and one finite synthetic sample, so a single number hides how much it would
# wobble under resampling.  To report the comparison "in the most accurate way"
# we resample customers (with replacement, carrying + relabelling each
# customer's transactions) B times, recompute every metric, and report the
# median together with a 95% percentile confidence interval.
#
# Within each bootstrap iteration the *same* resampled real dataset is shared
# across all methods (common random numbers), so method-vs-method differences
# are measured on identical draws — the ranking is then trustworthy, not noise.

def _txn_index(transactions: pd.DataFrame) -> dict:
    """Pre-group transactions by customer_id once, for fast resampling."""
    return {cid: g for cid, g in transactions.groupby("customer_id")}


def _resample(customers: pd.DataFrame, txn_index: dict,
              rng: np.random.Generator, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Customer-level bootstrap resample.  Draws len(customers) customers with
    replacement and relabels customer_id (and transaction_id) so duplicated
    customers stay distinct — keeping groupby, key-uniqueness and referential
    integrity valid for the metrics and SDMetrics reports.
    """
    n = len(customers)
    idx = rng.integers(0, n, n)
    cust = customers.iloc[idx].reset_index(drop=True).copy()
    new_ids = [f"{prefix}{i:06d}" for i in range(n)]

    txn_parts, tcounter = [], 0
    for new_id, orig_id in zip(new_ids, cust["customer_id"].to_numpy()):
        g = txn_index.get(orig_id)
        if g is None or len(g) == 0:
            continue
        gg = g.copy()
        gg["customer_id"] = new_id
        gg["transaction_id"] = [f"{prefix}T{tcounter + k:07d}" for k in range(len(gg))]
        tcounter += len(gg)
        txn_parts.append(gg)

    cust["customer_id"] = new_ids
    txn = (pd.concat(txn_parts, ignore_index=True)
           if txn_parts else customers.iloc[0:0].copy())
    return cust, txn


def _ci(series: pd.Series) -> dict:
    s = series.dropna()
    if s.empty:
        return {"median": np.nan, "ci_low": np.nan, "ci_high": np.nan, "std": np.nan}
    return {
        "median":  round(float(s.median()), 4),
        "ci_low":  round(float(s.quantile(0.025)), 4),
        "ci_high": round(float(s.quantile(0.975)), 4),
        "std":     round(float(s.std()), 4),
    }


def bootstrap_compare_methods(real_data: dict,
                              synthetic_datasets: dict[str, dict],
                              n_boot: int = 200,
                              n_boot_privacy: int = 40,
                              priv_subsample: int = 500,
                              seed: int = 0,
                              progress_every: int = 25) -> dict:
    """
    Bootstrap every metric across methods.

    Returns a dict with:
      "raw"      : long DataFrame, one row per (method, iteration) with all metrics
      "summary"  : tidy DataFrame indexed by method, columns
                   "<metric>_median", "<metric>_ci_low", "<metric>_ci_high"

    Cheap metrics (quality / diagnostic / cross-table / temporal) use n_boot
    iterations; the expensive privacy metrics use n_boot_privacy iterations with
    a smaller subsample (DCR cost grows ~quadratically with subsample size).
    """
    import warnings
    rng = np.random.default_rng(seed)
    real_idx = _txn_index(real_data["transactions"])
    syn_idx  = {m: _txn_index(s["transactions"]) for m, s in synthetic_datasets.items()}

    rows = []
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    for b in range(n_boot):
        if progress_every and b % progress_every == 0:
            print(f"  bootstrap {b}/{n_boot} …", flush=True)
        # Shared resampled real for this iteration (common random numbers).
        rc, rt = _resample(real_data["customers"], real_idx, rng, prefix="R")
        real_b = {"customers": rc, "transactions": rt}
        do_priv = b < n_boot_privacy

        for name, syn in synthetic_datasets.items():
            sc, st = _resample(syn["customers"], syn_idx[name], rng, prefix="S")
            syn_b = {"customers": sc, "transactions": st}
            row = {"method": name, "iter": b}

            try:
                row.update(_sdmetrics_scores(real_b, syn_b))
            except Exception as e:
                print(f"    ⚠ SDMetrics ({name}, b={b}): {e}")
            try:
                ct = cross_table_score(rc, rt, sc, st)
                row["cross_table_mad"] = ct["mean_abs_delta"]
            except Exception as e:
                print(f"    ⚠ Cross-table ({name}, b={b}): {e}")
            try:
                ts = temporal_score(rt, st)
                row["ia_ks_pvalue"] = ts["ia_ks_pvalue"]
                row["autocorr_mae"] = ts["autocorr_mae"]
            except Exception as e:
                print(f"    ⚠ Temporal ({name}, b={b}): {e}")
            if do_priv:
                try:
                    row.update(privacy_scores(rc, sc, subsample=priv_subsample))
                except Exception as e:
                    print(f"    ⚠ Privacy ({name}, b={b}): {e}")
            rows.append(row)

    raw = pd.DataFrame(rows)
    metrics = [c for c in raw.columns if c not in ("method", "iter")]
    summary_rows = []
    for name, g in raw.groupby("method"):
        rec = {"method": name}
        for m in metrics:
            ci = _ci(g[m])
            rec[f"{m}_median"]  = ci["median"]
            rec[f"{m}_ci_low"]  = ci["ci_low"]
            rec[f"{m}_ci_high"] = ci["ci_high"]
        summary_rows.append(rec)
    summary = pd.DataFrame(summary_rows).set_index("method")
    return {"raw": raw, "summary": summary}


def format_ci_table(summary: pd.DataFrame,
                    metrics: list[str] | None = None) -> pd.DataFrame:
    """Render the bootstrap summary as 'median [low, high]' strings per metric."""
    if metrics is None:
        metrics = [c[:-len("_median")] for c in summary.columns
                   if c.endswith("_median")]
    out = {}
    for m in metrics:
        med, lo, hi = f"{m}_median", f"{m}_ci_low", f"{m}_ci_high"
        if med in summary.columns:
            out[m] = [f"{summary.loc[i, med]:.3f} [{summary.loc[i, lo]:.3f}, "
                      f"{summary.loc[i, hi]:.3f}]" for i in summary.index]
    return pd.DataFrame(out, index=summary.index)


def compare_methods(real_data: dict,
                    synthetic_datasets: dict[str, dict]) -> pd.DataFrame:
    """
    real_data           : {"customers": df, "transactions": df}
    synthetic_datasets  : {"Method 1 – HMA GC": {...}, "Method 2 – CTGAN": {...}, ...}
    Returns a tidy DataFrame with all metrics as columns, methods as rows.
    """
    rows = []
    for method_name, syn in synthetic_datasets.items():
        print(f"  Evaluating: {method_name} …")
        row = {"method": method_name}

        # Standard metrics
        try:
            std = _sdmetrics_scores(real_data, syn)
            row.update(std)
        except Exception as e:
            print(f"    ⚠ SDMetrics error: {e}")

        # Cross-table correlation
        try:
            ct = cross_table_score(
                real_data["customers"], real_data["transactions"],
                syn["customers"],       syn["transactions"],
            )
            row["cross_table_mad"]     = ct["mean_abs_delta"]
            row["cross_table_max_err"] = ct["max_abs_delta"]
        except Exception as e:
            print(f"    ⚠ Cross-table error: {e}")

        # Temporal realism
        try:
            ts = temporal_score(real_data["transactions"], syn["transactions"])
            row["ia_ks_pvalue"]   = ts["ia_ks_pvalue"]
            row["ia_ks_stat"]     = ts["ia_ks_statistic"]
            row["autocorr_mae"]   = ts["autocorr_mae"]
            row["syn_ia_mean"]    = ts["syn_ia_mean"]
        except Exception as e:
            print(f"    ⚠ Temporal error: {e}")

        rows.append(row)

    df = pd.DataFrame(rows).set_index("method")
    return df

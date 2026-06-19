"""
Method 5 — SmartNoise MST (differentially private).

SmartNoise (OpenDP) synthesizes data under a formal (ε, δ)-differential-privacy
guarantee, which none of the SDV methods provide.  MST is a marginal-based DP
synthesizer (private-PGM): it spends the ε budget measuring low-order marginals
under the Gaussian/Laplace mechanism, then samples from a graphical model fit to
those noisy marginals.

Design (mirrors the independent-table SDV methods M2/M4):
  - customers and transactions are fit separately; IDs are dropped before fitting
    (high-cardinality identifiers would shatter the privacy budget) and
    regenerated afterwards.
  - transaction_date is encoded as an integer day-offset (continuous) for fitting
    and decoded back to a date on sampling.
  - DP synthesizers do not accept SDV constraints, so business rules are restored
    by *post-processing* (clipping to valid domains, mapping product_id→category).
    Post-processing a DP output preserves the DP guarantee.

Privacy budget: ``epsilon`` is spent per table (sequential composition), so the
customers+transactions pipeline costs ~2·epsilon total at the chosen δ.
"""


import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from snsynth import Synthesizer

from .schema import PRODUCTS

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

START_DATE = pd.Timestamp(date(2022, 1, 1))
END_DATE   = pd.Timestamp(date(2025, 12, 31))
MAX_DAY    = (END_DATE - START_DATE).days
PRODUCT_CAT = {p["product_id"]: p["category"] for p in PRODUCTS}

CUST_CAT  = ["gender", "education", "occupation", "marital_status", "region", "is_churned"]
CUST_CONT = ["age", "income", "num_dependents", "credit_score", "tenure_years"]
TXN_CAT   = ["product_id", "product_category", "channel", "status", "is_first_product"]
TXN_CONT  = ["amount", "date_ordinal"]


def _encode_transactions(t_df: pd.DataFrame) -> pd.DataFrame:
    t = t_df.drop(columns=["transaction_id", "customer_id"]).copy()
    t["transaction_date"] = pd.to_datetime(t["transaction_date"])
    t["date_ordinal"] = (t["transaction_date"] - START_DATE).dt.days.clip(0, MAX_DAY)
    return t.drop(columns=["transaction_date"])


def train_smartnoise(real_data: dict, epsilon: float = 3.0,
                     preprocessor_eps: float = 0.5, save: bool = True):
    c_df = real_data["customers"].drop(columns=["customer_id"])
    t_df = _encode_transactions(real_data["transactions"])

    sn_c = Synthesizer.create("mst", epsilon=epsilon, verbose=False)
    sn_c.fit(c_df, categorical_columns=CUST_CAT, continuous_columns=CUST_CONT,
             preprocessor_eps=preprocessor_eps)

    sn_t = Synthesizer.create("mst", epsilon=epsilon, verbose=False)
    sn_t.fit(t_df, categorical_columns=TXN_CAT, continuous_columns=TXN_CONT,
             preprocessor_eps=preprocessor_eps)

    # Note: MST synthesizers are not picklable (internal lambdas), so unlike the
    # SDV methods the fitted model isn't persisted — only the sampled CSVs are.
    return {"sn_customers": sn_c, "sn_transactions": sn_t, "epsilon": epsilon}


def _clean_customers(cust: pd.DataFrame, n: int) -> pd.DataFrame:
    cust = cust.reset_index(drop=True).copy()
    cust["age"]            = cust["age"].clip(18, 90).round().astype(int)
    cust["credit_score"]   = cust["credit_score"].clip(300, 850).round().astype(int)
    cust["num_dependents"] = cust["num_dependents"].clip(0, 6).round().astype(int)
    cust["income"]         = cust["income"].clip(lower=15_000).round(2)
    cust["tenure_years"]   = np.minimum(cust["tenure_years"].clip(lower=0.1),
                                        cust["age"]).round(1)
    cust["is_churned"]     = cust["is_churned"].astype(bool)
    cust.insert(0, "customer_id", [f"C{i:05d}" for i in range(1, n + 1)])
    return cust


def generate_smartnoise(models: dict, real_transactions: pd.DataFrame,
                        n_customers: int = 1000) -> dict:
    sn_c = models["sn_customers"]
    sn_t = models["sn_transactions"]

    cust = _clean_customers(sn_c.sample(n_customers), n_customers)

    # cardinality resampled from the real distribution (same as M2/M4)
    real_counts = real_transactions.groupby("customer_id").size().values
    counts      = np.random.choice(real_counts, size=n_customers, replace=True)
    total       = int(counts.sum())

    txn = sn_t.sample(total).reset_index(drop=True)
    txn["amount"] = txn["amount"].clip(lower=0).round(2)
    day = txn["date_ordinal"].clip(0, MAX_DAY).round().astype(int)
    txn["transaction_date"] = START_DATE + pd.to_timedelta(day, unit="D")
    txn = txn.drop(columns=["date_ordinal"])
    # restore product_id → product_category (DP can't take FixedCombinations)
    txn["product_category"] = txn["product_id"].map(PRODUCT_CAT).fillna(txn["product_category"])
    txn["is_first_product"] = txn["is_first_product"].astype(bool)

    # attach FK customer_id by cardinality, regenerate transaction_id
    cids = np.repeat(cust["customer_id"].values, counts)
    txn = txn.iloc[:len(cids)].copy()
    txn["customer_id"] = cids
    txn.insert(0, "transaction_id", [f"T{i:06d}" for i in range(len(txn))])

    cols = ["transaction_id", "customer_id", "product_id", "product_category",
            "amount", "transaction_date", "channel", "status", "is_first_product"]
    txn = txn[[c for c in cols if c in txn.columns]]
    return {"customers": cust, "transactions": txn}

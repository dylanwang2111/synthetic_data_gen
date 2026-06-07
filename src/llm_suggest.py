"""
LLM-powered product suggestion using customer profile + transaction history.

Supports two backends:
  - Claude (Anthropic) — prompt caching on the product catalog
  - DeepSeek           — OpenAI-compatible API (deepseek-chat)
"""

import json
import os
import anthropic
from openai import OpenAI
import pandas as pd

from .schema import PRODUCTS

_CATALOG_TEXT = "\n".join(
    f"- {p['product_id']} | {p['name']} | Category: {p['category']} | "
    f"Min Amount: ${p['min_amount']:,.0f} | Risk: {p['risk_level']} | Premium: {p['is_premium']}"
    for p in PRODUCTS
)

SYSTEM_PROMPT = f"""You are a financial product advisor for a bank. \
Your task is to recommend the most suitable products to a customer \
based on their demographic profile and transaction history.

Available products:
{_CATALOG_TEXT}

Rules:
- Only recommend products NOT already held by the customer.
- Rank by expected fit (highest fit first).
- Give exactly 3 recommendations.
- Respond in JSON with this schema:
  {{"recommendations": [{{"product_id": "...", "name": "...", "reason": "..."}}]}}
"""


def _build_profile(
    customer: pd.Series,
    transactions: pd.DataFrame,
) -> str:
    held = (
        transactions[transactions["customer_id"] == customer["customer_id"]]
        [["product_id", "amount", "channel"]]
        .drop_duplicates("product_id")
        .to_dict("records")
    )
    return json.dumps(
        {
            "customer": {
                "age":            int(customer["age"]),
                "gender":         customer["gender"],
                "income":         round(float(customer["income"]), 2),
                "education":      customer["education"],
                "occupation":     customer["occupation"],
                "marital_status": customer["marital_status"],
                "region":         customer["region"],
                "num_dependents": int(customer["num_dependents"]),
                "credit_score":   int(customer["credit_score"]),
                "tenure_years":   float(customer["tenure_years"]),
            },
            "current_products": held,
        },
        indent=2,
    )


def _suggest_claude(profile: str, model: str) -> tuple[dict, dict]:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Customer profile:\n{profile}"}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    tokens = {
        "input":          response.usage.input_tokens,
        "cache_creation": getattr(response.usage, "cache_creation_input_tokens", 0),
        "cache_read":     getattr(response.usage, "cache_read_input_tokens", 0),
    }
    return json.loads(raw), tokens


def _suggest_deepseek(profile: str, model: str, api_key: str) -> tuple[dict, dict]:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    response = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Customer profile:\n{profile}"},
        ],
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    tokens = {
        "input":          response.usage.prompt_tokens,
        "cache_creation": 0,
        "cache_read":     getattr(response.usage, "prompt_cache_hit_tokens", 0),
    }
    return json.loads(raw), tokens


def suggest(
    customer_id: str,
    customers_df: pd.DataFrame,
    transactions_df: pd.DataFrame,
    model: str = "deepseek-chat",
    deepseek_api_key: str | None = None,
) -> dict:
    row = customers_df[customers_df["customer_id"] == customer_id]
    if row.empty:
        raise ValueError(f"Customer {customer_id} not found")

    profile = _build_profile(row.iloc[0], transactions_df)

    use_deepseek = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
    if use_deepseek:
        key = deepseek_api_key or os.environ["DEEPSEEK_API_KEY"]
        recs, tokens = _suggest_deepseek(profile, model, key)
    else:
        recs, tokens = _suggest_claude(profile, model)

    recs["customer_id"]  = customer_id
    recs["cache_tokens"] = tokens
    return recs


def batch_suggest(
    customer_ids: list[str],
    customers_df: pd.DataFrame,
    transactions_df: pd.DataFrame,
    model: str = "deepseek-chat",
    deepseek_api_key: str | None = None,
) -> list[dict]:
    results = []
    for cid in customer_ids:
        try:
            r = suggest(cid, customers_df, transactions_df, model, deepseek_api_key)
            results.append(r)
        except Exception as exc:
            results.append({"customer_id": cid, "error": str(exc)})
    return results

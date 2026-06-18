"""
SDV Constraint-Augmented Generation (CAG) definitions for the pipeline.

SDV 1.x exposes programmatic constraints through ``sdv.cag``.  Constraints are
attached to a synthesizer with ``synth.add_constraints([...])`` *before* fitting;
SDV then guarantees the rule holds in every sampled row (reverse-transforming or
rejection-sampling as needed) instead of leaving it to chance.

transactions  ·  product_category rule  (FixedCombinations)
-----------------------------------------------------------
``product_category`` is denormalised from ``product_id`` — each product belongs
to exactly one category in the catalog.  A plain synthesizer can emit a
``product_id``/``product_category`` pair that never existed (e.g. a Banking
product tagged "Investment").  ``FixedCombinations`` restricts the synthetic
data to combinations actually observed in the real data, eliminating those
invalid pairings.

Note: ``FixedCombinations`` requires the columns to be ``categorical`` (or
``boolean``).  In the 2-table comparison schema ``product_id`` is categorical,
so the constraint applies cleanly; the single-table metadata builders force
``product_id`` to categorical for the same reason.

customers  ·  whole-number dependents  (FixedIncrements)
--------------------------------------------------------
``num_dependents`` is a count — it must be a non-negative whole number.
``FixedIncrements`` with ``increment_value=1`` forces the synthesizer to emit
integers (no "2.4 dependents"), independent of how the column is represented.
Requires the column to be ``numerical``; the single-table metadata builders
force ``num_dependents`` to numerical so the constraint applies.

Bounded / relational fields  (ScalarRange · ScalarInequality · Inequality)
--------------------------------------------------------------------------
- ``credit_score`` must stay within the FICO range [300, 850]  → ScalarRange.
- ``amount`` (transactions) must be non-negative                → ScalarInequality.
- ``tenure_years`` cannot exceed the customer's ``age``          → Inequality.

``ScalarRange`` and ``ScalarInequality`` bound a column against constants; the
modern ``sdv.cag`` module does not export them, so they are passed in SDV's
legacy *dict* form (``{"constraint_class": ..., "constraint_parameters": ...}``),
which ``add_constraints`` still accepts.  ``Inequality`` (a column-vs-column rule)
is a native ``sdv.cag`` class.  All three can be mixed in one ``add_constraints``
call alongside the CAG objects above.
"""

from sdv.cag import FixedCombinations, FixedIncrements, Inequality


def product_category_constraint(table_name: str | None = None) -> FixedCombinations:
    """
    Each ``product_id`` maps to exactly one ``product_category``.

    table_name : pass the table name for multi-table synthesizers (e.g.
                 HMASynthesizer → "transactions"); leave ``None`` for
                 single-table synthesizers (CTGAN / TVAE / PAR on transactions).
    """
    return FixedCombinations(
        column_names=["product_id", "product_category"],
        table_name=table_name,
    )


def num_dependents_constraint(table_name: str | None = None) -> FixedIncrements:
    """``num_dependents`` is a whole number (integer count)."""
    return FixedIncrements(
        column_name="num_dependents",
        increment_value=1,
        table_name=table_name,
    )


def _scalar_range(column: str, low, high, table_name: str | None = None,
                  strict: bool = False) -> dict:
    """ScalarRange (column bounded by two constants) in SDV's legacy dict form."""
    spec = {
        "constraint_class": "ScalarRange",
        "constraint_parameters": {
            "column_name": column,
            "low_value": low,
            "high_value": high,
            "strict_boundaries": strict,
        },
    }
    if table_name:
        spec["table_name"] = table_name
    return spec


def _scalar_inequality(column: str, relation: str, value,
                       table_name: str | None = None) -> dict:
    """ScalarInequality (column vs a constant) in SDV's legacy dict form."""
    spec = {
        "constraint_class": "ScalarInequality",
        "constraint_parameters": {
            "column_name": column,
            "relation": relation,
            "value": value,
        },
    }
    if table_name:
        spec["table_name"] = table_name
    return spec


def credit_score_constraint(table_name: str | None = None) -> dict:
    """``credit_score`` stays within the FICO range [300, 850]."""
    return _scalar_range("credit_score", 300, 850, table_name=table_name)


def amount_constraint(table_name: str | None = None) -> dict:
    """``amount`` must be non-negative."""
    return _scalar_inequality("amount", ">=", 0, table_name=table_name)


def tenure_age_constraint(table_name: str | None = None) -> Inequality:
    """``tenure_years`` cannot exceed ``age``."""
    return Inequality(
        low_column_name="tenure_years",
        high_column_name="age",
        table_name=table_name,
    )


def transaction_constraints(multi_table: bool = False,
                            sequential: bool = False) -> list:
    """
    Constraint list for the transactions table.

    sequential : set ``True`` for PARSynthesizer.  ``FixedCombinations`` merges
                 ``product_id``/``product_category`` into one column, which PAR
                 then mis-handles as a per-sequence context column (it varies
                 within a customer's sequence) and rejects.  PAR therefore gets
                 only the scalar ``amount`` constraint.
    """
    table = "transactions" if multi_table else None
    cons = [amount_constraint(table_name=table)]
    if not sequential:
        cons.insert(0, product_category_constraint(table_name=table))
    return cons


def customer_constraints(multi_table: bool = False) -> list:
    """Constraint list for the customers table."""
    table = "customers" if multi_table else None
    return [
        num_dependents_constraint(table_name=table),
        credit_score_constraint(table_name=table),
        tenure_age_constraint(table_name=table),
    ]

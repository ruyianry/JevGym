"""Curated Kalshi category → series registry for expanding the dataset.

Kalshi market payloads omit the category (it lives on the series), so we stamp the category at
ingest time; the snapshot builder's ``DOMAIN_MAP`` then maps it to a domain, which controls how
evidence (macro trends, prior decisions) is attached. Only series verified to have **settled
markets with candlesticks** are listed here — no fabrication.

Recurring series (CPI, payrolls, the Fed, FX pairs, gas prices, earnings…) benefit most from the
"prior decisions" enrichment; ``economics`` markets additionally pick up FRED macro-trend
evidence. Both are timestamped and leakage-safe.

``GATED_CATEGORY_SERIES`` holds sensitive categories (elections / geopolitics). They are **not**
in the default set — you must request them explicitly, and the snapshot builder marks them
``sensitive`` so they are quarantined from the default publish.
"""

from __future__ import annotations

# Default (non-sensitive) categories. category label (stamped on markets) -> series tickers.
CATEGORY_SERIES: dict[str, list[str]] = {
    "Economics": [
        "KXCPIYOY", "KXCPI", "KXPAYROLLS", "KXU3", "KXGDP", "KXEGGS", "KXFED", "KXFEDDECISION",
    ],
    "Cryptocurrencies": ["KXBTCD", "KXETHD"],
    "Climate and Weather": ["KXTORNADO"],
    "Sports": ["KXLNBPGAME", "KXLPGAR1LEAD", "KXNCAAF2QSPREAD", "KXLEAGUESCUPSPREAD"],
    "Companies": ["KXSPOT", "KXROKU", "KXAMZN"],
    "Financials": ["KXNZDUSD", "KXUSDMXNAW", "KXAUDUSDAW", "KXINXHUD"],
    "Science and Technology": ["KXOPENSHARE", "KXANTHTOKEND", "KXCRITICALITY"],
    "Commodities": ["KXAAAGASM", "KXWTIH", "KXAAAGASDFL"],
}

# Gated / sensitive categories — opt-in only; quarantined from the default publish.
GATED_CATEGORY_SERIES: dict[str, list[str]] = {
    "Elections": ["KXTRUMPNUMSTATES", "KXGOVFLNOMD", "KXZAMBIAPRES", "KXMANCHESTERMOV"],
}

# category label -> snapshot domain (mirrors builder.DOMAIN_MAP; kept dependency-free here)
CATEGORY_DOMAIN: dict[str, str] = {
    "Economics": "economics",
    "Cryptocurrencies": "crypto",
    "Climate and Weather": "weather",
    "Sports": "sports",
    "Companies": "companies",
    "Financials": "financials",
    "Science and Technology": "science",
    "Commodities": "commodities",
    "Elections": "politics",  # -> sensitive, gated
}

_ALL_SERIES = {**CATEGORY_SERIES, **GATED_CATEGORY_SERIES}

# series ticker -> snapshot domain (builder uses this when a market carries no category)
DOMAIN_BY_SERIES: dict[str, str] = {
    s: CATEGORY_DOMAIN[cat] for cat, series in _ALL_SERIES.items() for s in series
}


def series_for(categories: list[str] | None = None) -> list[str]:
    """All series for the given categories. Default (``None``) = every **non-gated** category;
    gated categories are only included when named explicitly."""
    cats = categories if categories is not None else list(CATEGORY_SERIES)
    out: list[str] = []
    for c in cats:
        out.extend(_ALL_SERIES.get(c, []))
    return out


def category_by_series(categories: list[str] | None = None) -> dict[str, str]:
    """series ticker -> category label, for stamping at ingest time."""
    cats = categories if categories is not None else list(CATEGORY_SERIES)
    return {s: c for c in cats for s in _ALL_SERIES.get(c, [])}

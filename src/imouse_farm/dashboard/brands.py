"""Dashboard brand definitions (Labely, ValCoin, …)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_BRAND_ID = "labely"

_BRANDS: dict[str, dict[str, str]] = {
    "labely": {
        "id": "labely",
        "name": "Labely",
        "mark": "L",
        "tagline": "TikTok automation",
        "accent": "#6366f1",
        "accent_hover": "#818cf8",
    },
    "valcoin": {
        "id": "valcoin",
        "name": "ValCoin",
        "mark": "V",
        "tagline": "TikTok automation",
        "accent": "#f59e0b",
        "accent_hover": "#fbbf24",
    },
}


def load_brands(path: str | Path = "config/brands.yaml") -> dict[str, dict[str, str]]:
    brand_path = Path(path)
    if not brand_path.exists():
        return dict(_BRANDS)
    with brand_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    merged = dict(_BRANDS)
    for brand_id, data in raw.items():
        if not isinstance(data, dict):
            continue
        base = dict(merged.get(str(brand_id), {}))
        base.update({k: str(v) for k, v in data.items() if v is not None})
        base["id"] = str(brand_id)
        merged[str(brand_id)] = base
    return merged


def get_brand(brand_id: str, brands: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    catalog = brands or _BRANDS
    key = str(brand_id or DEFAULT_BRAND_ID).strip().lower()
    return dict(catalog.get(key) or catalog[DEFAULT_BRAND_ID])


def render_dashboard_html(
    template_path: Path,
    *,
    brand_id: str,
    farm_slots: int,
    brands: dict[str, dict[str, str]] | None = None,
) -> str:
    brand = get_brand(brand_id, brands)
    html = template_path.read_text(encoding="utf-8")
    replacements: dict[str, str] = {
        "__FARM_SLOTS__": str(farm_slots),
        "__BRAND_ID__": brand["id"],
        "__APP_NAME__": brand["name"],
        "__APP_MARK__": brand.get("mark", brand["name"][:1]),
        "__APP_TAGLINE__": brand.get("tagline", "TikTok automation"),
        "__ACCENT_COLOR__": brand.get("accent", "#6366f1"),
        "__ACCENT_HOVER__": brand.get("accent_hover", "#818cf8"),
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html

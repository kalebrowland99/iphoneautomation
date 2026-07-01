"""Shared brand/slot storage key helpers."""

from __future__ import annotations

VALID_BRANDS = frozenset({"labely", "valcoin"})


def normalize_brand(brand: str) -> str:
    b = str(brand or "labely").strip().lower()
    return b if b in VALID_BRANDS else "labely"


def brand_profile_key(base_key: str, brand: str) -> str:
    """Storage key for a slot/device + brand, e.g. slot:3:valcoin."""
    base = str(base_key or "").strip()
    b = normalize_brand(brand)
    if not base:
        return f"unknown:{b}"
    parts = base.split(":")
    if parts and parts[-1] in VALID_BRANDS:
        base = ":".join(parts[:-1])
    return f"{base}:{b}"


def base_profile_key(key: str) -> str:
    """Strip brand suffix from a storage key (slot:3:valcoin → slot:3)."""
    parts = str(key or "").split(":")
    if parts and parts[-1] in VALID_BRANDS:
        return ":".join(parts[:-1])
    return str(key or "")


def device_storage_key(device_id: str, user_name: str = "") -> str:
    """Stable base key for a farm slot (no brand suffix)."""
    slot = str(user_name or "").strip().lower()
    return f"slot:{slot}" if slot else device_id


def text_key_for_device(
    device_id: str,
    user_name: str = "",
    *,
    brand: str = "labely",
) -> str:
    return brand_profile_key(device_storage_key(device_id, user_name), brand)

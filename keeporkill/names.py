"""Shared naming helpers for evidence packs and ruling artifacts."""

from __future__ import annotations

import re


def slugify_check(check):
    """Return the deterministic file name slug for one check name."""

    slug = re.sub(r"[^a-z0-9]+", "-", check.lower()).strip("-")
    if not slug:
        slug = "check"
    return slug[:48].rstrip("-") or "check"

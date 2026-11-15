"""Axis values: parsing specs like "400,700", "300:700" or "all", and planning
which static fonts / trimmed variable fonts to build.

    value  400        → pinned (static)
    range  300:700    → kept variable, limited to 300–700
    all               → every value the font's named instances use on that axis

Several axes multiply: --weight 400,700 --width 75,100 → 4 fonts.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from fontTools.ttLib import TTFont

from .common import FontmintError

Value = float | tuple[float, float]  # pinned value or (min, max) range


def parse_spec(spec) -> list:
    """'400,700' / '300:700' / 'all' / 400 / [400, (300, 700), 'all'] → list of items."""
    if isinstance(spec, (int, float)):
        return [float(spec)]
    if isinstance(spec, tuple) and len(spec) == 2 and all(isinstance(v, (int, float)) for v in spec):
        return [_normalize(spec)]  # (300, 700) is a range, like "300:700"
    if isinstance(spec, list):
        return [_parse_item(i) if isinstance(i, str) else _normalize(i) for i in spec]
    if isinstance(spec, str):
        items = [s.strip() for s in spec.split(",") if s.strip()]
        if not items:
            raise FontmintError("empty axis value (use a number, MIN:MAX or 'all')")
        return [_parse_item(i) for i in items]
    raise FontmintError(f"unsupported axis value: {spec!r}")


def _normalize(item):
    if isinstance(item, tuple) and len(item) == 2:
        lo, hi = float(min(item)), float(max(item))
        return lo if lo == hi else (lo, hi)
    if isinstance(item, (int, float)):
        return float(item)
    raise FontmintError(f"unsupported axis value: {item!r}")


def _parse_item(text: str):
    if text == "all":
        return "all"
    try:
        if ":" in text:
            return _normalize(tuple(float(x) for x in text.split(":", 1)))
        return float(text)
    except ValueError:
        raise FontmintError(f"invalid axis value '{text}' (use a number, MIN:MAX or 'all')") from None


@dataclass
class Plan:
    combos: list[dict[str, Value]]  # one dict per output, flagged axes only
    labeled: set[str]               # axes with several pinned values (need a style label)


def plan(font: TTFont, specs: dict[str, object]) -> Plan:
    """Expand axis specs against the font's fvar into output combinations."""
    fvar = font["fvar"]
    axes = {a.axisTag: a for a in fvar.axes}
    expanded: dict[str, list[Value]] = {}
    for tag, spec in specs.items():
        if tag not in axes:
            raise FontmintError(f"font has no '{tag}' axis (axes: {', '.join(axes)})")
        a = axes[tag]
        values: list[Value] = []
        try:
            items = parse_spec(spec)
        except FontmintError as e:
            raise FontmintError(f"axis {tag}: {e}") from None
        for item in items:
            if item == "all":
                named = sorted({i.coordinates[tag] for i in fvar.instances if tag in i.coordinates})
                if not named:
                    raise FontmintError(f"font has no named instances on the '{tag}' axis; "
                                       "give values instead of 'all'")
                values += named
                continue
            for v in item if isinstance(item, tuple) else (item,):
                if not a.minValue <= v <= a.maxValue:
                    raise FontmintError(f"{tag} {v:g} is outside the axis range {a.minValue:g}–{a.maxValue:g}")
            values.append(item)
        expanded[tag] = list(dict.fromkeys(values))

    tags = list(expanded)
    combos = [dict(zip(tags, vals)) for vals in itertools.product(*(expanded[t] for t in tags))]
    labeled = {t for t, vals in expanded.items() if sum(not isinstance(v, tuple) for v in vals) > 1}
    return Plan(combos, labeled)


def is_static(combo: dict[str, Value]) -> bool:
    return not any(isinstance(v, tuple) for v in combo.values())

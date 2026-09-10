"""Plain-language rendering for a client-facing lead digest email.

Written for Darren (a busy, non-technical contractor) as the reader, same
discipline `bidscraper_full.digest.send_resend.render_digest_html` already
holds for Jeff: no raw scores, no internal field/component names
("lead_score", "canopy_component", "pct_tree_canopy_nearby"), no decimals.
Every sentence is built directly from the parcel's own real signal values
(`year_built`, `pct_tree_canopy_nearby`, `nearest_storm_event_date`), not
from the 0-1 scoring components -- a plain description of "why this
property" doesn't need the scoring machinery, just the underlying facts.

Canopy copy branches on `extscorer.scoring.basic.canopy_score`'s own
optimal point rather than a second, independently-guessed percentage
threshold -- one source of truth for "what counts as heavy cover or fully
exposed," not two heuristics that could quietly drift apart.
"""
from __future__ import annotations

from typing import Any

from extscorer.scoring.basic import DEFAULT_CANOPY_OPTIMAL_PCT

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _format_storm_date(value: Any) -> str:
    return f"{_MONTH_NAMES[value.month - 1]} {value.day}, {value.year}"


def describe_lead(parcel: dict[str, Any], as_of_year: int) -> str:
    """One short, plain-language sentence set explaining why a property
    made the list -- built from real signal values, not internal scores.
    """
    clauses: list[str] = []

    year_built = parcel.get("year_built")
    if year_built is not None:
        age = as_of_year - year_built
        clauses.append(f"built in {year_built} ({age} years old)")

    pct = parcel.get("pct_tree_canopy_nearby")
    if pct is not None:
        pct = float(pct)
        if pct >= DEFAULT_CANOPY_OPTIMAL_PCT:
            clauses.append(f"heavy tree cover nearby ({pct:.0f}%), which can trap moisture and drop debris on a roof over time")
        else:
            clauses.append(f"little tree cover nearby ({pct:.0f}%), leaving the roof more exposed to sun and wind")

    storm_date = parcel.get("nearest_storm_event_date")
    if storm_date is not None:
        clauses.append(f"a storm was recorded in the area on {_format_storm_date(storm_date)}")

    if not clauses:
        return "On our list based on property age."
    # Capitalize only the first character -- str.capitalize() would also
    # lowercase everything after it (e.g. turning "May 19" into "may 19"),
    # which a real test caught.
    sentence = "; ".join(clauses) + "."
    return sentence[0].upper() + sentence[1:]


def render_digest_text(leads_with_parcels: list[tuple[Any, dict[str, Any]]], as_of_year: int) -> str:
    """Plain-text digest body -- the email's `text` fallback."""
    lines = [
        f"North East Corner Construction -- {len(leads_with_parcels)} Exterior Renovation Lead(s)",
        "",
        "These are homes in the Quiet Corner that look like good candidates for a siding or roofing",
        "conversation, based on how old the property is, the tree cover around it, and recent storm",
        "activity in the area.",
        "",
    ]
    for i, (lead, parcel) in enumerate(leads_with_parcels, start=1):
        lines.append(f"{i}. {parcel.get('address', 'Unknown address')}, {parcel.get('town', '')}")
        lines.append(f"   {describe_lead(parcel, as_of_year)}")
        lines.append("")
    return "\n".join(lines)


_COLOR_INK = "#1a1a2e"
_COLOR_MUTED = "#6b7280"
_COLOR_ACCENT = "#2f7d4f"  # a construction-adjacent green, not electric's amber
_COLOR_BORDER = "#e5e7eb"
_COLOR_PANEL = "#f9fafb"
_FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _esc(value: Any) -> str:
    import html as html_lib

    return html_lib.escape(str(value)) if value is not None else ""


def render_digest_html(leads_with_parcels: list[tuple[Any, dict[str, Any]]], as_of_year: int) -> str:
    """A single self-contained HTML email -- inline styles only, no
    external assets, same rendering-reliability discipline as Tool 1's
    own `render_digest_html`.
    """
    rows = []
    for i, (lead, parcel) in enumerate(leads_with_parcels, start=1):
        address = _esc(parcel.get("address", "Unknown address"))
        town = _esc(parcel.get("town", ""))
        description = _esc(describe_lead(parcel, as_of_year))
        rows.append(
            f'<div style="padding:16px 0;border-top:1px solid {_COLOR_BORDER};">'
            f'<div style="font-size:12px;color:{_COLOR_MUTED};">#{i}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{_COLOR_INK};margin-top:2px;">{address}, {town}</div>'
            f'<div style="font-size:14px;color:{_COLOR_INK};margin-top:6px;line-height:1.5;">{description}</div>'
            f"</div>"
        )

    body = f"""\
<div style="background-color:#f3f4f6;padding:24px 12px;font-family:{_FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background-color:#ffffff;border-radius:8px;overflow:hidden;border:1px solid {_COLOR_BORDER};">
<tr><td style="padding:0;">
<div style="background-color:{_COLOR_INK};padding:28px 32px;">
  <div style="color:#ffffff;font-size:20px;font-weight:700;">North East Corner Construction</div>
  <div style="color:#c7cad1;font-size:14px;margin-top:4px;">Exterior Renovation Lead Report &middot; {len(leads_with_parcels)} propert{'y' if len(leads_with_parcels) == 1 else 'ies'}</div>
</div>
<div style="padding:20px 32px 4px;font-size:13px;color:{_COLOR_MUTED};line-height:1.6;">
  These are homes in the Quiet Corner that look like good candidates for a siding or roofing
  conversation, based on how old the property is, the tree cover around it, and recent storm
  activity in the area.
</div>
<div style="padding:0 32px 12px;">
  {''.join(rows)}
</div>
<div style="padding:16px 32px 24px;border-top:1px solid {_COLOR_BORDER};background-color:{_COLOR_PANEL};">
  <div style="font-size:12px;color:{_COLOR_MUTED};line-height:1.6;">
    Based on town property records, NOAA tree-canopy data, and NOAA storm history for Windham County, CT.
  </div>
</div>
</td></tr>
</table>
</div>"""
    return body

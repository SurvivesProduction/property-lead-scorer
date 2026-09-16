"""Plain-language rendering for a client-facing lead digest email.

Written for Darren (a busy, non-technical contractor) as the reader, same
discipline `bidscraper_full.digest.send_resend.render_digest_html` already
holds for Jeff: no raw scores, no internal field/component names
("lead_score", "canopy_component", "pct_tree_canopy_nearby"), no decimals.
Every sentence is built directly from the parcel's own real signal values
(`year_built`, `exterior_wall_1`, `most_recent_exterior_permit_date`,
`pct_tree_canopy_nearby`, `nearest_storm_event_date`), not from the 0-1
scoring components -- a plain description of "why this property" doesn't
need the scoring machinery, just the underlying facts.

Canopy copy branches on `extscorer.scoring.basic.canopy_score`'s own
optimal point rather than a second, independently-guessed percentage
threshold -- one source of truth for "what counts as heavy cover or fully
exposed," not two heuristics that could quietly drift apart.

**Standing rule (added 2026-09-15, Prompt T):** this module's copy must be
updated in the SAME prompt as any change to `extscorer.scoring.basic`'s
signals or weights -- not treated as a separate, later ask. The siding
signal became the second-highest-weighted factor (Prompt S) and this
file went a full prompt without mentioning it at all, which a real
digest send surfaced as a real gap: Killingly/Ashford/Woodstock leads
were showing up on the list for reasons the copy never explained. Check
this file's own clause list against `score_property`'s active signals
whenever either changes.

**Storm clause is visually de-emphasized in HTML (added 2026-09-15,
Prompt U)**: the storm-recency clause is IDENTICAL across every real
lead as of this writing (see `extscorer.scoring.basic`'s own module
docstring -- `storm_score` is still a pure constant across the whole real
population), so it carries no real differentiating information for the
reader even though it's a real fact. `describe_lead_parts` splits it out
from the other clauses so the HTML renderer can style it smaller/lighter
than the real differentiating signals (property age, siding, canopy)
without it visually competing for attention. The plain-text renderer has
no such styling concept, so `describe_lead` still folds it into one
sentence for that path.
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


def _describe_siding(parcel: dict[str, Any], as_of_year: int) -> str | None:
    """One clause on the siding material+age signal -- the second-highest
    -weighted signal after property age (see `extscorer.scoring.basic`'s
    module docstring, "Siding signal" section). Built from the same real
    fields `real_siding_age_score`/`siding_age_score` read
    (`exterior_wall_1`, `permit_data_available`, `most_recent_exterior_
    permit_date`), never from `siding_component` itself -- same "facts,
    not scores" discipline as every other clause here.

    Returns `None` when there's no siding material on file at all (a
    real, if now rarer, gap -- see `real_siding_age_score`'s own "missing
    material" case), so a property with no siding data simply gets no
    siding clause rather than a fabricated one.

    Three real cases, in order of how much this module actually knows:
    a permit-tracked property (Killingly/Ashford/Woodstock) with a real
    exterior-relevant permit on file names the material AND says when it
    was last worked on -- the most informative case, and the only one
    that can happen for a property that STILL made a top-lead list (a
    very recent permit would score low enough to not be here at all, so
    a permit clause on a real lead means real, but non-recent, work).
    A permit-tracked property with NO exterior permit on file says the
    material and that town records show no exterior work ever done --
    real confirmation, not a guess. Everywhere else (the 5 towns without
    real permit tracking), the material is named as the proxy's own basis
    without claiming permit visibility that doesn't exist for that town.
    """
    exterior_wall_1 = parcel.get("exterior_wall_1")
    if not exterior_wall_1:
        return None
    material = exterior_wall_1.lower()
    # Some real material values already say "siding" themselves (e.g.
    # "Aluminum Siding", or a real compound value like "Wood Shingles/
    # Clapboards" that happens to follow one that does) -- don't append a
    # second, redundant "siding" onto those.
    material_phrase = material if "siding" in material else f"{material} siding"

    if parcel.get("permit_data_available"):
        most_recent = parcel.get("most_recent_exterior_permit_date")
        if most_recent is not None:
            years_since = as_of_year - most_recent.year
            return f"the {material_phrase} was last worked on in {most_recent.year} ({years_since} years ago, per town permit records)"
        return f"town permit records show no exterior work ever done on the {material_phrase}"
    return f"the exterior siding ({material}) looks original to the house, based on town property records"


def _capitalize_sentence(clauses: list[str]) -> str:
    # Capitalize only the first character -- str.capitalize() would also
    # lowercase everything after it (e.g. turning "May 19" into "may 19"),
    # which a real test caught.
    sentence = "; ".join(clauses) + "."
    return sentence[0].upper() + sentence[1:]


def _describe_main_clauses(parcel: dict[str, Any], as_of_year: int) -> list[str]:
    """Property age, siding, and canopy clauses, in that order -- the
    signals' own weight order (see `extscorer.scoring.basic`'s module
    docstring) minus storm, which `describe_lead_parts` renders
    separately (see this module's own "Storm clause" docstring note).
    """
    clauses: list[str] = []

    year_built = parcel.get("year_built")
    if year_built is not None:
        age = as_of_year - year_built
        clauses.append(f"built in {year_built} ({age} years old)")

    siding_clause = _describe_siding(parcel, as_of_year)
    if siding_clause is not None:
        clauses.append(siding_clause)

    pct = parcel.get("pct_tree_canopy_nearby")
    if pct is not None:
        pct = float(pct)
        if pct >= DEFAULT_CANOPY_OPTIMAL_PCT:
            clauses.append(f"heavy tree cover nearby ({pct:.0f}%), which can trap moisture and drop debris on a roof over time")
        else:
            clauses.append(f"little tree cover nearby ({pct:.0f}%), leaving the roof more exposed to sun and wind")

    return clauses


def _describe_storm(parcel: dict[str, Any]) -> str | None:
    storm_date = parcel.get("nearest_storm_event_date")
    if storm_date is None:
        return None
    return f"a storm was recorded in the area on {_format_storm_date(storm_date)}"


def describe_lead(parcel: dict[str, Any], as_of_year: int) -> str:
    """One short, plain-language sentence explaining why a property made
    the list -- built from real signal values, not internal scores. Used
    by the plain-text renderer, which has no way to visually de-emphasize
    the storm clause the way `describe_lead_parts` lets the HTML renderer
    do -- folds every clause (including storm) into one sentence.
    """
    clauses = _describe_main_clauses(parcel, as_of_year)
    storm_clause = _describe_storm(parcel)
    if storm_clause is not None:
        clauses.append(storm_clause)

    if not clauses:
        return "On our list based on property age."
    return _capitalize_sentence(clauses)


def describe_lead_parts(parcel: dict[str, Any], as_of_year: int) -> tuple[str, str | None]:
    """(main_sentence, storm_sentence) -- used by the HTML renderer to
    style the storm clause smaller/lighter than the real differentiating
    signals (see this module's own "Storm clause" docstring note).
    `storm_sentence` is `None` when there's no storm data on file, same
    as every other "not on file" convention here.
    """
    clauses = _describe_main_clauses(parcel, as_of_year)
    main_sentence = _capitalize_sentence(clauses) if clauses else "On our list based on property age."

    storm_clause = _describe_storm(parcel)
    storm_sentence = _capitalize_sentence([storm_clause]) if storm_clause is not None else None

    return main_sentence, storm_sentence


def render_digest_text(leads_with_parcels: list[tuple[Any, dict[str, Any]]], as_of_year: int) -> str:
    """Plain-text digest body -- the email's `text` fallback."""
    lines = [
        f"North East Corner Construction -- {len(leads_with_parcels)} Exterior Renovation Lead(s)",
        "",
        "These are homes in the Quiet Corner that look like good candidates for a siding or roofing",
        "conversation, based on how old the property is, its current siding, the tree cover around it,",
        "and recent storm activity in the area.",
        "",
    ]
    for i, (lead, parcel) in enumerate(leads_with_parcels, start=1):
        lines.append(f"{i}. {parcel.get('address', 'Unknown address')}, {parcel.get('town', '')}")
        lines.append(f"   {describe_lead(parcel, as_of_year)}")
        source_url = parcel.get("source_url")
        if source_url:
            lines.append(f"   Verify this property: {source_url}")
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
        main_sentence, storm_sentence = describe_lead_parts(parcel, as_of_year)
        description = _esc(main_sentence)
        if storm_sentence is not None:
            # Smaller, lighter-weight, muted-color -- identical across
            # every property (see module docstring), so it shouldn't
            # visually compete with the real differentiating signals in
            # the sentence above it.
            description += (
                f' <span style="font-size:11px;font-weight:400;color:{_COLOR_MUTED};">{_esc(storm_sentence)}</span>'
            )

        # Only ever link a real, already-stored per-record URL -- never
        # fabricate or guess one (this project's standing "only hyperlink
        # where a real stable URL exists" rule). `source_url` is our own
        # scraper's own VGSI/propertyrecordcards.com card link, trusted
        # content from our own database, not user input -- still escaped
        # defensively before going into the href.
        source_url = parcel.get("source_url")
        verify_link = ""
        if source_url:
            verify_link = (
                f'<div style="margin-top:8px;">'
                f'<a href="{_esc(source_url)}" style="font-size:12px;color:{_COLOR_ACCENT};text-decoration:none;font-weight:600;">'
                f"Verify this property &rarr;</a></div>"
            )

        rows.append(
            f'<div style="padding:16px 0;border-top:1px solid {_COLOR_BORDER};">'
            f'<div style="font-size:12px;color:{_COLOR_MUTED};">#{i}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{_COLOR_INK};margin-top:2px;">{address}, {town}</div>'
            f'<div style="font-size:14px;color:{_COLOR_INK};margin-top:6px;line-height:1.5;">{description}</div>'
            f"{verify_link}"
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
  conversation, based on how old the property is, its current siding, the tree cover around it,
  and recent storm activity in the area.
</div>
<div style="padding:0 32px 12px;">
  {''.join(rows)}
</div>
<div style="padding:16px 32px 24px;border-top:1px solid {_COLOR_BORDER};background-color:{_COLOR_PANEL};">
  <div style="font-size:12px;color:{_COLOR_MUTED};line-height:1.6;">
    Based on town property and permit records, NOAA tree-canopy data, and NOAA storm history for Windham County, CT.
  </div>
</div>
</td></tr>
</table>
</div>"""
    return body

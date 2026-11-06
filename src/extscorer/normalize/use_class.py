"""Parcel `use_class`: is this parcel a home we can sell exterior work on?

Values (the `parcels.use_class` column, migration 012):

- `residential`: a dwelling (single and multi-family, condo unit, mobile or manufactured home).
- `farm_forest_residential`: a dwelling on land assessed as farm or forest ("Use Assessment").
  Stays eligible: these are real houses (many are 18th-century farmhouses).
- `non_residential`: industrial, commercial, school, church, municipal or other institutional.
  Still scored, but excluded from the digest, the Job Board export and mail drops.
- `unknown`: no evidence, or genuinely mixed (a church-owned residence, "Residential Business",
  vacant land). Stays eligible: exclusion needs positive evidence.

## Evidence order (first tier that recognises the value wins)

1. **State CAMA description** (`raw_data["State_Use_Description"]`, or the lower-case
   `state_use_description` Windham's Socrata load stores): exact lookup of the normalised value in
   `_STATE_DESCRIPTION_CLASS`.
2. **Source description**: propertyrecordcards.com `raw_data["property_use"]` in
   `_PRC_PROPERTY_USE_CLASS`, then VGSI `raw_data["style"]` in `_VGSI_STYLE_CLASS`.
3. **Regex** over whichever of those texts exist, ONLY for a spelling no table has seen (a new town,
   a new card template). The result's source is `"regex"` so a backfill report can count how often it
   was needed.

The tables were generated on 2026-11-05 from every distinct value on a scored parcel (140 state
descriptions, 13 propertyrecordcards uses, 45 VGSI styles), then reviewed by hand. Spellings vary by
town (`"Single Fam  MDL-01"`, `"SFR (NL)"`), so values are normalised first: lower-cased, the
`MDL-nn` / `Mnn` model suffixes dropped, whitespace collapsed.
"""
from __future__ import annotations

import re
from typing import Any

RESIDENTIAL = "residential"
FARM_FOREST_RESIDENTIAL = "farm_forest_residential"
NON_RESIDENTIAL = "non_residential"
UNKNOWN = "unknown"
USE_CLASSES = (RESIDENTIAL, FARM_FOREST_RESIDENTIAL, NON_RESIDENTIAL, UNKNOWN)

_MODEL_SUFFIX_RE = re.compile(r"\s*\bmdl[ -]?\d+\b|\s+m\d{2}\b|\s+md\d{2}\b")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_use_text(value: str | None) -> str:
    text = (value or "").lower().strip()
    text = _MODEL_SUFFIX_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip(" -")


_STATE_DESCRIPTION_CLASS: dict[str, str] = {
    '1 fam (nl)': 'residential',
    '2 family': 'residential',
    '3 family': 'residential',
    '4 family': 'residential',
    '5 - 8 fam': 'residential',
    'acclnd mfg': 'non_residential',
    'apartment': 'residential',
    'apt - 4 unit': 'residential',
    'apt - over 8': 'residential',
    'apt 4+ units': 'residential',
    'apt 4-unt': 'residential',
    'apt 5+up': 'residential',
    'apt over 8': 'residential',
    'audobon': 'non_residential',
    'auto repair': 'non_residential',
    'auto repr': 'non_residential',
    'auto s s&s': 'non_residential',
    'auto v s&s': 'non_residential',
    'bank bldg': 'non_residential',
    'charitable': 'non_residential',
    'charitable- res': 'unknown',
    'child care': 'non_residential',
    'church': 'non_residential',
    'church - comm': 'non_residential',
    'church - res': 'unknown',
    'church hse': 'unknown',
    'church sch': 'non_residential',
    'cnty hist': 'non_residential',
    'comm bldg': 'non_residential',
    'comm land': 'non_residential',
    'comm whse': 'non_residential',
    'condo': 'residential',
    'condo nl': 'residential',
    'condominium': 'residential',
    'conv food': 'non_residential',
    'county': 'non_residential',
    'county vfd': 'non_residential',
    'ct state': 'non_residential',
    'day care': 'non_residential',
    'educ bldg': 'non_residential',
    'event barn': 'unknown',
    'factory': 'non_residential',
    'farm bldgs': 'unknown',
    'fire dept': 'non_residential',
    'fish&game': 'non_residential',
    'four famil': 'residential',
    'four familly': 'residential',
    'fratnl org': 'non_residential',
    'fuel sv/pr': 'non_residential',
    'funeral hm': 'non_residential',
    'gas st srv': 'non_residential',
    'golf crse': 'non_residential',
    'group home': 'unknown',
    'health clb': 'non_residential',
    'historical': 'non_residential',
    'historical bldg': 'non_residential',
    'hsng auth': 'non_residential',
    'ind bldg': 'non_residential',
    'ind office': 'non_residential',
    'ind whse': 'non_residential',
    'inns': 'non_residential',
    'inns/res': 'unknown',
    'lumber yrd': 'non_residential',
    'manufactured home': 'residential',
    'mh park': 'non_residential',
    'mobile hom': 'residential',
    'mobile home': 'residential',
    'mobile wf': 'residential',
    'mobilehome': 'residential',
    'motels': 'non_residential',
    'multi houses': 'residential',
    'multi hses': 'residential',
    'mun bldg com': 'non_residential',
    'mun bldg res': 'unknown',
    'mun fire': 'non_residential',
    'mun library': 'non_residential',
    'mun park bldg': 'non_residential',
    'mun pub sc': 'non_residential',
    'mun town': 'non_residential',
    'museums': 'non_residential',
    'non p camp': 'non_residential',
    'non profit - comm': 'non_residential',
    'non-profit': 'non_residential',
    'non-profit bldg': 'non_residential',
    'non-profit camp bldg': 'non_residential',
    'non-profit res': 'unknown',
    'nursing hm': 'non_residential',
    'off condo': 'non_residential',
    'office': 'non_residential',
    'office bld': 'non_residential',
    'office bldg': 'non_residential',
    'over 8 fam': 'residential',
    'parish hse': 'unknown',
    'post off': 'non_residential',
    'post office': 'non_residential',
    'pri res': 'unknown',
    'prof bldg': 'non_residential',
    'pub school': 'non_residential',
    'pvt coll': 'non_residential',
    'pvt school': 'non_residential',
    'pvt school com': 'non_residential',
    'pvt school res': 'unknown',
    'religious': 'non_residential',
    'res / comm': 'unknown',
    'res dwelling': 'residential',
    'residential': 'residential',
    'residential business': 'unknown',
    'rest/clubs': 'non_residential',
    'rtl gas st': 'non_residential',
    's&g': 'non_residential',
    'sand & gravel': 'non_residential',
    'sfr (nl)': 'residential',
    'sfr w/inlaw': 'residential',
    'shopngmall': 'non_residential',
    'shopping mall': 'non_residential',
    'sin fam w/ in-law': 'residential',
    'single fam': 'residential',
    'single fam w in-law': 'residential',
    'single fam w/in-law': 'residential',
    'single fam+acc unit': 'residential',
    'single family': 'residential',
    'single family w/ in-law': 'residential',
    'state - comm': 'non_residential',
    'state - res': 'unknown',
    'state adm': 'non_residential',
    'state bldg res': 'unknown',
    'state corr': 'non_residential',
    'state dot bldg': 'non_residential',
    'state rec': 'non_residential',
    'store': 'non_residential',
    'store/shop': 'non_residential',
    'super market': 'non_residential',
    'tel x sta': 'non_residential',
    'three fam': 'residential',
    'three family': 'residential',
    'town hall': 'non_residential',
    'trailer': 'residential',
    'trailer nl': 'residential',
    'two family': 'residential',
    'us gov': 'non_residential',
    'use assessment': 'farm_forest_residential',
    'vet org': 'non_residential',
    'vol fire dept': 'non_residential',
}


# Added 2026-11-06 for the Putnam and Griswold state-CAMA loads (spellings the regex tier would
# otherwise have to guess at). Same review as the table above.
_STATE_DESCRIPTION_CLASS.update(
    {
        '1-family': 'residential',
        '2-family': 'residential',
        'sf with in-law': 'residential',
        'res. condo': 'residential',
        'sfr water': 'residential',
        'sfr/inlaw': 'residential',
    }
)

_PRC_PROPERTY_USE_CLASS: dict[str, str] = {
    'apartments': 'residential',
    'automotive': 'non_residential',
    'church/nonprofit': 'non_residential',
    'elderly': 'unknown',
    'entertainment': 'non_residential',
    'industrial': 'non_residential',
    'nonprofit/church': 'non_residential',
    'office': 'non_residential',
    'public use': 'non_residential',
    'residential': 'residential',
    'restaurant': 'non_residential',
    'retail': 'non_residential',
    'vacant land': 'unknown',
}

_VGSI_STYLE_CLASS: dict[str, str] = {
    'antique': 'residential',
    'apartments': 'residential',
    'bungalow': 'residential',
    'camp': 'unknown',
    'cape': 'residential',
    'cape cod': 'residential',
    'churches': 'non_residential',
    'clubs/lodges': 'non_residential',
    'colonial': 'residential',
    'comm/apt': 'unknown',
    'commercial': 'non_residential',
    'condominium': 'residential',
    'contemporary': 'residential',
    'conventional': 'residential',
    'cottage': 'residential',
    'duplex': 'residential',
    'family conver.': 'residential',
    'fire station': 'non_residential',
    'four family': 'residential',
    'garrison colonial': 'residential',
    'gas mart': 'non_residential',
    'light indust': 'non_residential',
    'manufactured home': 'residential',
    'mobile home': 'residential',
    'modern/contemp': 'residential',
    'multi family': 'residential',
    'office bldg': 'non_residential',
    'old style': 'residential',
    'other': 'unknown',
    'pre-eng garage': 'non_residential',
    'raised ranch': 'residential',
    'ranch': 'residential',
    'restaurant': 'non_residential',
    'salt box': 'residential',
    'seasonal': 'residential',
    'service shop': 'non_residential',
    'split level': 'residential',
    'split-level': 'residential',
    'store': 'non_residential',
    'three family': 'residential',
    'townhouse': 'residential',
    'trailer': 'residential',
    'two family': 'residential',
    'warehouse': 'non_residential',
    'year round': 'residential',
}


# --- tier 3: last-resort regex, for a spelling none of the tables has seen -----------------

_REGEX_UNKNOWN = re.compile(
    r"res ?/ ?comm|residential business|inns?/res|church - res|church hse|parish hse|non-?profit res|"
    r"charit\w*[- ]+res|pvt school res|mun bldg res|state (?:bldg )?- ?res|group home|elderly|comm/apt|"
    r"farm bldgs|event barn|vacant|condo main|\bcamp\b"
)
_REGEX_NON_RESIDENTIAL = re.compile(
    r"store|shop|retail|office|\bofc\b|bank|rest|club|lodge|\binns?\b|motel|hotel|garage|auto|gas|fuel|comm|"
    r"prof|conv food|super ?market|mall|funeral|day ?care|child care|school|educ|college|\bcoll\b|church|"
    r"relig|parish|chapel|non-?profit|charit|fratnl|vet org|post off|\bmun\b|town hall|county|cnty|fire|"
    r"police|library|\bstate\b|us gov|\bfed|hsng|housing auth|hist|museum|\bpark\b|golf|sand|gravel|"
    r"\bs&g\b|lumber|factory|\bind\b|indust|whse|warehouse|mfg|nursing|health|hospital|fish|utility|"
    r"cemetery|public|\bpub\b|entertainment|manuf(?!actured)|cinema|theat|marina|storage"
)
_REGEX_RESIDENTIAL = re.compile(
    r"single|sfr|sin fam|\b1 ?fam|two fam|\b2 ?fam|three|\b3 ?fam|four|\b4 ?fam|multi|\bapt|apartment|condo|"
    r"mobil|manufactured|trailer|^residential$|dwelling|townhouse|ranch|colonial|cape|cottage|bungalow|"
    r"split|raised|contemp|antique|conventional|duplex|garrison|salt ?box|old style|year round|seasonal"
)
_REGEX_DWELLING_OVERRIDE = re.compile(r"mobil|manufactured|trailer|townhouse|single|two fam|\bapt")


def _regex_class(text: str) -> str:
    if _REGEX_UNKNOWN.search(text):
        return UNKNOWN
    if _REGEX_NON_RESIDENTIAL.search(text) and not _REGEX_DWELLING_OVERRIDE.search(text):
        return NON_RESIDENTIAL
    if _REGEX_RESIDENTIAL.search(text):
        return RESIDENTIAL
    return UNKNOWN


def _has_dwelling(parcel: dict[str, Any]) -> bool:
    return bool(parcel.get("year_built")) and bool(parcel.get("living_area_sqft"))


def classify_use_class_with_source(parcel: dict[str, Any]) -> tuple[str, str]:
    """`(use_class, source)`; `source` is `state_cama`, `prc_property_use`, `vgsi_style`, `regex` or
    `none`, so a dry-run can report how much rests on the regex tier.
    """
    raw = parcel.get("raw_data") or {}
    state_text = raw.get("State_Use_Description") or raw.get("state_use_description")
    prc_text = raw.get("property_use")
    vgsi_text = raw.get("style")

    candidates = (
        ("state_cama", state_text, _STATE_DESCRIPTION_CLASS),
        ("prc_property_use", prc_text, _PRC_PROPERTY_USE_CLASS),
        ("vgsi_style", vgsi_text, _VGSI_STYLE_CLASS),
    )
    for source, text, table in candidates:
        key = normalize_use_text(text)
        if key and key in table:
            use_class = table[key]
            if use_class == FARM_FOREST_RESIDENTIAL and not _has_dwelling(parcel):
                return UNKNOWN, source  # farm/forest LAND with no building is not a home
            return use_class, source

    for text in (state_text, prc_text, vgsi_text):
        key = normalize_use_text(text)
        if key:
            return _regex_class(key), "regex"
    return UNKNOWN, "none"


def classify_use_class(parcel: dict[str, Any]) -> str:
    return classify_use_class_with_source(parcel)[0]

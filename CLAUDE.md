# property-lead-scorer (Tool 4, public half)

Client: **Darren, North East Corner Construction** — a SEPARATE client
from Elite Electric (Tools 1-3/[[elite-electric]]). CT "Quiet Corner"
(Windham County) property-level lead scorer for exterior renovation
(siding/roofing) work, from property age + tree canopy + storm history +
real siding/permit data (where available). Package `extscorer` (NOT
`leadscorer` — that's Tool 2's name, different client). `client_id =
'north-east-corner-construction'`.

Read `README.md` first. No ARCHITECTURE.md of its own — the sibling
`property-lead-scorer-full/ARCHITECTURE.md` is canonical for this tool.

- **Don't assume Tools 1-3's conventions apply** — several were
  deliberately changed here (two normalized schemas not one, no DB-backed
  sources registry, etc.), for documented reasons in the `-full` repo's
  ARCHITECTURE.md.
- Reuses Elite Electric's shared Supabase project (a deliberate client
  decision, not physical separation) — `client_id` tagging is
  load-bearing for keeping this data apart from Elite Electric's.
- No known Desktop deploy-only clone for this tool (unlike Tools 1-3) —
  verify before assuming one exists.
- Only commit/push when explicitly asked.

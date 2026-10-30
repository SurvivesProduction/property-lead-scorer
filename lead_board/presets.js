/*
 * Named weight presets for the interactive slider Lead Board.
 *
 * `storm` is included in every preset for completeness (the combine
 * formula in `scoring.js` reads it the same as any other weight), but
 * Step 0 confirmed `score_storm_component` is a pure constant (a single
 * shared `nearest_storm_event_date` value) across literally all 24,578
 * real scoreable parcels -- the storm slider is DISABLED in the page UI
 * ("county-wide constant, no differentiation yet"), so its weight here
 * never actually changes any ranking regardless of preset.
 */
'use strict';

const PRESETS = {
  darren_default: {
    label: 'Darren default',
    description: "Current config weights -- property age leads, siding close behind, canopy and storm supporting. This is what's actually driving today's Sheet/digest picks.",
    weights: {
      property: 0.5,
      canopy: 0.15,
      storm: 0.05,
      siding: 0.3,
      jobSize: 0,
      saleRecency: 0,
    },
  },
  // **Siding-focused: property_weight dropped to 0, 2026-10-30
  // follow-up.** The original version (property=0.30, siding=0.50)
  // measured 19-20/20 overlap with Darren default against the real
  // population -- not a bug in the weights, a structural fact about the
  // two curves: `_durable_material_age_score` saturates to 1.0 for an
  // old-enough durable-sided house, same ceiling `property_age_score`
  // itself approaches for the exact same house -- so ANY property_weight
  // > 0 keeps pinning the identical ancient-durable-sided properties at
  // the top regardless of how heavily siding is weighted alongside it
  // (confirmed directly: even siding_weight=1.0/property_weight=0.0
  // alone still returns a 100%-durable-material top 20, not a single
  // vinyl house -- vinyl's own curve caps at 0.60
  // (`DEFAULT_SIDING_VINYL_MODERATE_HIGH_SCORE`), strictly below
  // durable's 1.0 ceiling, so no linear reweighting of the real
  // `score_property` components can ever surface a vinyl-sided house
  // over a durable-sided one. A "Vinyl-era" preset, as literally
  // proposed, is not buildable without a material filter under this
  // project's current scoring formula.)
  //
  // Fix: drop `property` to 0 entirely (removes the ceiling-tie problem
  // at its root) and add canopy (0.15, a second REAL differentiator
  // independent of age) and job size (0.10, tiebreaks among otherwise-
  // tied maxed-siding properties by square footage) so the ranking
  // actually moves. Measured against the real population: 7/20 overlap
  // with Darren default (target was <=14/20), 11/20 with Bigger Jobs
  // (a different cut, not a near-duplicate of it) -- siding stays the
  // single heaviest weight (0.70), preserving the preset's original
  // intent ("lead with siding condition"), just without the age anchor
  // that was silently overriding it.
  siding_focused: {
    label: 'Siding-focused',
    description: 'Siding is the dominant signal (0.70); property age is deliberately ZERO (it was silently pinning the same ancient-durable-sided houses at the top as the default weights -- durable siding\'s own curve saturates at the same ceiling property age does). Canopy (0.15) and job size (0.10) differentiate among otherwise-tied maxed-siding properties instead.',
    weights: {
      property: 0,
      canopy: 0.15,
      storm: 0.05,
      siding: 0.7,
      jobSize: 0.1,
      saleRecency: 0,
    },
  },
  bigger_jobs: {
    label: 'Bigger jobs',
    description: 'Job size (from living sqft, falling back to assessed value) becomes meaningful at 0.35 -- the single heaviest signal -- but property age stays a close second at 0.30 rather than being crowded out, since an old house with overdue siding is still the core pitch; siding/canopy/storm all step down to make room.',
    weights: {
      property: 0.3,
      canopy: 0.1,
      storm: 0.05,
      siding: 0.2,
      jobSize: 0.35,
      saleRecency: 0,
    },
  },
};

if (typeof module !== 'undefined') {
  module.exports = { PRESETS };
}

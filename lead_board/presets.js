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
  siding_focused: {
    label: 'Siding-focused',
    description: 'Siding becomes the heaviest signal (0.50, up from 0.30) -- for a call where the crew wants to lead with "whose siding is visibly overdue" rather than "whose house is oldest." Property age stays second (0.30, down from 0.50) since it is still real evidence, just no longer the lead signal; canopy/storm unchanged.',
    weights: {
      property: 0.3,
      canopy: 0.15,
      storm: 0.05,
      siding: 0.5,
      jobSize: 0,
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

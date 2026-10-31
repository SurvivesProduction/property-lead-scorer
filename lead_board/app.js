/*
 * Page wiring for the interactive slider Lead Board -- DOM rendering and
 * event handling only. Not required()'d by the Node tests (no DOM in
 * Node) -- validated instead by Playwright screenshots (Prompt W Step 5).
 * Depends on globals defined by scoring.js/filters.js/presets.js/state.js,
 * which the build scripts inline BEFORE this file in the final page, and
 * on a global `LEAD_BOARD_DATA` object (the export JSON, or the demo
 * fixture) injected the same way.
 */
(function () {
  'use strict';

  const DATA = window.LEAD_BOARD_DATA;
  const PARCELS = DATA.parcels;
  const SOLD_TOWNS = DATA.metadata.sold_towns || [];
  const ALL_TOWNS = Array.from(new Set(PARCELS.map((p) => p.town))).sort();

  // Set only by `build_lead_board.py`'s `--teaser` build (2026-10-30
  // visibility/polish follow-up) -- real/share never set this, so every
  // branch below is a no-op for them (identical to today's behavior).
  const IS_TEASER = Boolean(DATA.metadata && DATA.metadata.is_teaser);

  // 'Unknown' is included automatically whenever any parcel lacks the
  // field -- materialsOf/roofCoverOf (filters.js) both bucket missing
  // data there, so it's always a real, selectable option rather than a
  // silently-dropped filter value.
  const ALL_SIDING_MATERIALS = Array.from(new Set(PARCELS.flatMap((p) => materialsOf(p)))).sort();
  const ALL_ROOF_MATERIALS = Array.from(new Set(PARCELS.map((p) => roofCoverOf(p)))).sort();
  const HAS_STATE_ONLY_DATA = PARCELS.some((p) => p.flags.is_state_only);

  // ---- percentile tables, computed ONCE over the full population ----
  const sortedSqft = PARCELS.map((p) => p.living_area_sqft).filter((v) => v !== null && v !== undefined).sort((a, b) => a - b);
  const sortedAssessedValue = PARCELS.map((p) => p.assessed_value).filter((v) => v !== null && v !== undefined).sort((a, b) => a - b);
  const sortedSaleYears = PARCELS.map((p) => p.last_sale_year).filter((v) => v !== null && v !== undefined).sort((a, b) => a - b);

  // A teaser row carries jobSize/saleRecency PRECOMPUTED server-side
  // (scripts/build_lead_board.py's `build_teaser_data`, percentile rank
  // against the share population) instead of the raw living_area_sqft/
  // assessed_value/last_sale_year this function would otherwise need --
  // those raw fields are stripped entirely from teaser rows specifically
  // so no viewer can read them back out. Use the precomputed value
  // whenever a row already has one; only fall back to computing it from
  // raw fields (every other build) when it doesn't.
  const jobSizeByLeadKey = new Map();
  const saleRecencyByLeadKey = new Map();
  for (const p of PARCELS) {
    const precomputedJobSize = p.components && p.components.jobSize;
    const precomputedSaleRecency = p.components && p.components.saleRecency;
    jobSizeByLeadKey.set(
      p.lead_key,
      precomputedJobSize !== null && precomputedJobSize !== undefined
        ? precomputedJobSize
        : computeJobSizeComponent(p, sortedSqft, sortedAssessedValue)
    );
    saleRecencyByLeadKey.set(
      p.lead_key,
      precomputedSaleRecency !== null && precomputedSaleRecency !== undefined
        ? precomputedSaleRecency
        : computeSaleRecencyComponent(p, sortedSaleYears)
    );
  }

  const DEFAULT_WEIGHTS = PRESETS.darren_default.weights;

  // ---- live state ----
  let state = Object.assign({}, DEFAULT_FILTER_STATE, {
    weights: Object.assign({}, DEFAULT_WEIGHTS),
    activePreset: 'darren_default',
    topN: 20,
  });

  const fromHash = window.location.hash ? decodeState(window.location.hash.slice(1)) : null;
  if (fromHash) {
    state = Object.assign({}, state, fromHash);
  }

  // ---- DOM refs ----
  const el = (id) => document.getElementById(id);
  const root = el('app-root');

  function fmtPct(x) {
    return `${Math.round(x * 100)}%`;
  }

  function renderTownChips() {
    const container = el('town-chips');
    container.innerHTML = '';
    ALL_TOWNS.forEach((town) => {
      const claimed = isClaimedTerritory({ town }, SOLD_TOWNS);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip' + (state.towns && state.towns.has(town) ? ' chip-active' : '');
      chip.textContent = town + (claimed ? ' · claimed' : '');
      chip.addEventListener('click', () => {
        const towns = state.towns ? new Set(state.towns) : new Set();
        if (towns.has(town)) towns.delete(town);
        else towns.add(town);
        state.towns = towns.size > 0 ? towns : null;
        renderAll();
      });
      container.appendChild(chip);
    });
  }

  const FAMILY_LABELS = {
    vinyl: 'Vinyl',
    durable_original: 'Durable (wood/brick/etc)',
    other: 'Other',
    asphalt: 'Asphalt',
    metal: 'Metal',
    slate: 'Slate',
    wood: 'Wood',
    rubber_rolled: 'Rubber/Rolled',
    tar_gravel: 'Tar & Gravel',
    concrete: 'Concrete',
    Unknown: 'Unknown',
  };

  /**
   * Facet counts for a material filter -- how many parcels would match
   * if every OTHER currently-active filter/toggle stayed applied but
   * THIS dimension's own selection were cleared. Standard faceted-search
   * convention: lets a viewer see what's reachable without a chip
   * disappearing the instant they click it (clicking only narrows the
   * RESULTS, not the chip's own count basis).
   */
  function computeFacetCounts(options, bucketFn, excludeStateKey) {
    const baseState = Object.assign({}, state, { [excludeStateKey]: null });
    const matching = applyFilters(PARCELS, baseState, SOLD_TOWNS, jobSizeByLeadKey);
    const counts = new Map(options.map((o) => [o, 0]));
    matching.forEach((p) => {
      bucketFn(p).forEach((bucket) => {
        if (counts.has(bucket)) counts.set(bucket, counts.get(bucket) + 1);
      });
    });
    return counts;
  }

  function renderMaterialChips(containerId, options, stateKey, bucketFn) {
    const container = el(containerId);
    container.innerHTML = '';
    const counts = computeFacetCounts(options, bucketFn, stateKey);
    options
      .filter((option) => counts.get(option) > 0)
      .forEach((option) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip' + (state[stateKey] && state[stateKey].has(option) ? ' chip-active' : '');
        chip.textContent = `${FAMILY_LABELS[option] || option} (${counts.get(option)})`;
        chip.addEventListener('click', () => {
          const selected = state[stateKey] ? new Set(state[stateKey]) : new Set();
          if (selected.has(option)) selected.delete(option);
          else selected.add(option);
          state[stateKey] = selected.size > 0 ? selected : null;
          renderAll();
        });
        container.appendChild(chip);
      });
  }

  function slider(id, label, key, min, max, step, disabled, note) {
    return `
      <div class="control">
        <label for="${id}">${label}: <span id="${id}-val">${state.weights[key].toFixed(2)}</span></label>
        <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${state.weights[key]}" ${disabled ? 'disabled' : ''}>
        ${note ? `<div class="note">${note}</div>` : ''}
      </div>`;
  }

  function renderControls() {
    el('weight-sliders').innerHTML = [
      slider('w-property', 'Property age', 'property', 0, 1, 0.01, false),
      slider('w-canopy', 'Tree canopy', 'canopy', 0, 1, 0.01, false),
      slider('w-siding', 'Siding', 'siding', 0, 1, 0.01, false),
      slider('w-storm', 'Storm history', 'storm', 0, 1, 0.01, true, 'County-wide constant, no differentiation yet.'),
      slider('w-jobsize', 'Job size', 'jobSize', 0, 1, 0.01, false),
      slider('w-salerecency', 'Sale recency', 'saleRecency', 0, 1, 0.01, false),
    ].join('');

    ['property', 'canopy', 'siding', 'jobsize', 'salerecency'].forEach((idKey, i) => {
      const key = ['property', 'canopy', 'siding', 'jobSize', 'saleRecency'][i];
      const input = el(`w-${idKey}`);
      input.addEventListener('input', () => {
        state.weights[key] = parseFloat(input.value);
        state.activePreset = null;
        el(`w-${idKey}-val`).textContent = state.weights[key].toFixed(2);
        renderResults();
        syncHash();
      });
    });

    el('preset-buttons').innerHTML = Object.keys(PRESETS)
      .map((key) => `<button type="button" class="preset-btn${state.activePreset === key ? ' preset-btn-active' : ''}" data-preset="${key}" title="${PRESETS[key].description}">${PRESETS[key].label}</button>`)
      .join('');
    Array.from(el('preset-buttons').querySelectorAll('button')).forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-preset');
        state.weights = Object.assign({}, PRESETS[key].weights);
        state.activePreset = key;
        renderAll();
      });
    });

    refreshChips();

    // __TEASER_STRIP_START__
    el('toggle-claimed').checked = state.hideClaimed;
    el('toggle-worked').checked = state.hideWorked;
    el('toggle-mailed').checked = state.hideMailed;
    el('toggle-unreachable').checked = state.hideUnreachable;
    // __TEASER_STRIP_END__
    el('toggle-state-only').checked = state.showStateOnly;
    el('toggle-permit-history').checked = state.requireRealPermitHistory;
    // The toggle hides itself when the embedded dataset carries no
    // state-only rows at all (the --share build, see build_lead_board.py)
    // -- flipping it would do nothing, so don't offer it.
    el('toggle-state-only-row').style.display = HAS_STATE_ONLY_DATA ? '' : 'none';

    el('top-n').value = String(state.topN);
  }

  // Siding/roof chip COUNTS depend on every other active filter/toggle
  // (see computeFacetCounts) -- any handler that changes a filter/toggle
  // other than the chips themselves must refresh the chip groups too, or
  // their counts go stale. Deliberately NOT a full `renderControls()`
  // rebuild here: that would also re-create the filter <input> elements,
  // dropping focus/cursor position while a viewer is still typing in a
  // range field -- this only touches the chip containers.
  function refreshChips() {
    renderTownChips();
    renderMaterialChips('siding-chips', ALL_SIDING_MATERIALS, 'sidingMaterials', materialsOf);
    renderMaterialChips('roof-chips', ALL_ROOF_MATERIALS, 'roofCoverMaterials', (p) => [roofCoverOf(p)]);
  }

  function bindStaticControls() {
    // __TEASER_STRIP_START__
    el('toggle-claimed').addEventListener('change', (e) => { state.hideClaimed = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    el('toggle-worked').addEventListener('change', (e) => { state.hideWorked = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    el('toggle-mailed').addEventListener('change', (e) => { state.hideMailed = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    el('toggle-unreachable').addEventListener('change', (e) => { state.hideUnreachable = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    // __TEASER_STRIP_END__
    el('toggle-state-only').addEventListener('change', (e) => { state.showStateOnly = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    el('toggle-permit-history').addEventListener('change', (e) => { state.requireRealPermitHistory = e.target.checked; refreshChips(); renderResults(); syncHash(); });
    el('top-n').addEventListener('change', (e) => { state.topN = parseInt(e.target.value, 10); renderResults(); syncHash(); });

    ['year-min', 'year-max', 'canopy-min', 'canopy-max', 'jobsize-min', 'jobsize-max'].forEach((id) => {
      el(id).addEventListener('input', () => {
        const v = el(id).value;
        const num = v === '' ? null : parseFloat(v);
        if (id === 'year-min') state.yearBuiltMin = num;
        if (id === 'year-max') state.yearBuiltMax = num;
        if (id === 'canopy-min') state.canopyMin = num;
        if (id === 'canopy-max') state.canopyMax = num;
        if (id === 'jobsize-min') state.jobSizePctMin = num;
        if (id === 'jobsize-max') state.jobSizePctMax = num;
        refreshChips();
        renderResults();
        syncHash();
      });
    });

    el('copy-settings').addEventListener('click', () => {
      const json = settingsToClipboardJson(state);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(json);
      }
      const status = el('copy-status');
      status.textContent = 'Copied!';
      setTimeout(() => { status.textContent = ''; }, 1500);
    });

    el('theme-toggle').addEventListener('click', () => {
      // Must read the EFFECTIVE current scheme, not just whether
      // `data-theme` has been explicitly set -- a page that's never been
      // toggled has no attribute at all and is rendering purely from
      // `prefers-color-scheme`. Checking only the attribute meant a
      // system-dark visitor's first click set `data-theme="dark"`
      // explicitly, which is the SAME appearance already showing -- a
      // no-op click that only became visible on the second press.
      const explicit = document.documentElement.getAttribute('data-theme');
      const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const currentlyDark = explicit ? explicit === 'dark' : systemPrefersDark;
      document.documentElement.setAttribute('data-theme', currentlyDark ? 'light' : 'dark');
    });
  }

  function leadRowHtml(lead, defaultRankByLeadKey) {
    // Both ranks are positions WITHIN THE SAME FILTERED SET (see
    // renderResults) -- a lead's arrow answers "did the current weights
    // move this lead up/down among what's visible right now," never "...
    // among the whole 24,578-parcel population," which would be
    // meaningless once a viewer has narrowed to one town or one material.
    const defaultRank = defaultRankByLeadKey.get(lead.lead_key);
    const delta = defaultRank - lead.rank; // positive = moved up
    let arrow = '<span class="rank-same">—</span>';
    if (delta > 0) arrow = `<span class="rank-up">▲ ${delta}</span>`;
    else if (delta < 0) arrow = `<span class="rank-down">▼ ${Math.abs(delta)}</span>`;

    // A teaser row's year_built is already the DECADE (e.g. 1700, not
    // 1732) -- build_lead_board.py's build_teaser_data coarsens it for
    // re-identification reasons (see that module's own docstring); show
    // it as "1700s" rather than the bare, misleadingly-precise-looking
    // "1700" a plain exact year would otherwise print as.
    const yearLabel = lead.year_built
      ? (DATA.metadata && DATA.metadata.year_built_granularity === 'decade' ? `${lead.year_built}s` : lead.year_built)
      : '—';

    const stateOnlyBadge = lead.flags.is_state_only
      ? '<span class="badge badge-state-only">state data only, not verified</span>'
      : '';
    const recordLink = lead.source_url
      ? `<a href="${lead.source_url}" target="_blank" rel="noopener" class="verify-link">View record card</a>`
      : '<span class="verify-link verify-link-none">No record link</span>';
    // No placeholder when there's no usable address (see export_lead_
    // board_data.py's own `_map_url` docstring) -- omitted cleanly,
    // same "neither link, not a broken one" rule a missing source_url
    // does NOT get (that one still shows an explicit "No record link").
    const mapLink = lead.map_url
      ? `<a href="${lead.map_url}" target="_blank" rel="noopener" class="verify-link">See it on the map</a>`
      : '';

    const components = lead._components || {};
    const COMPONENT_LABELS = {
      property: 'Property age',
      canopy: 'Tree canopy',
      siding: 'Siding',
      storm: 'Storm history',
      jobSize: 'Job size',
      saleRecency: 'Sale recency',
    };
    const bars = ['property', 'canopy', 'siding', 'storm', 'jobSize', 'saleRecency']
      .filter((k) => components[k] !== null && components[k] !== undefined)
      .map((k) => `<div class="bar-row"><span class="bar-label">${COMPONENT_LABELS[k]}</span><div class="bar-track"><div class="bar-fill" style="width:${fmtPct(components[k])}"></div></div></div>`)
      .join('');

    return `
      <li class="lead-row" data-lead-key="${lead.lead_key}" data-rank="${lead.rank}">
        <div class="lead-row-main">
          <span class="lead-rank">#${lead.rank}</span>
          <span class="lead-arrow">${arrow}</span>
          <span class="lead-town">${lead.town}</span>
          <span class="lead-built">built ${yearLabel}</span>
          ${stateOnlyBadge}
          <button type="button" class="expand-btn" data-key="${lead.lead_key}">details</button>
        </div>
        <div class="lead-row-detail" id="detail-${cssSafe(lead.lead_key)}" hidden>
          ${bars}
          <div class="link-row">${recordLink}${mapLink}</div>
        </div>
      </li>`;
  }

  function cssSafe(key) {
    return key.replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  /**
   * One line, always visible above the results list, so a viewer never
   * has to open the (now-collapsible) Filters panel just to see what's
   * currently narrowing the list.
   */
  function summarizeFilters(state) {
    const parts = [];
    if (IS_TEASER) {
      // __TEASER_STRIP_START__
      // Every default exclusion (claimed/worked/contacted/unreachable/
      // state-only) is already applied SERVER-SIDE before the 250 rows
      // are even selected (see build_lead_board.py's build_teaser_data)
      // -- the ops toggles themselves are omitted from this build too
      // (see the public repo's template.html/app.js), so there's nothing
      // live left to summarize here. One static, always-true fact
      // replaces it.
      // __TEASER_STRIP_END__
      if (SOLD_TOWNS.length) {
        parts.push(`${SOLD_TOWNS.slice().sort().join(', ')}: territory already claimed.`);
      }
    } else {
      // __TEASER_STRIP_START__
      const hidden = [];
      if (state.hideClaimed) hidden.push('claimed');
      if (state.hideWorked) hidden.push('worked');
      if (state.hideMailed) hidden.push('mailed/shown');
      if (state.hideUnreachable) hidden.push('unreachable');
      if (hidden.length) parts.push(`Hiding ${hidden.join(', ')}`);
      // __TEASER_STRIP_END__
      if (state.showStateOnly) parts.push('showing state-data-only rows');
    }
    if (state.towns && state.towns.size) parts.push(`Towns: ${Array.from(state.towns).sort().join(', ')}`);
    if (state.sidingMaterials && state.sidingMaterials.size) {
      parts.push(`Siding: ${Array.from(state.sidingMaterials).map((f) => FAMILY_LABELS[f] || f).join(', ')}`);
    }
    if (state.roofCoverMaterials && state.roofCoverMaterials.size) {
      parts.push(`Roof: ${Array.from(state.roofCoverMaterials).map((f) => FAMILY_LABELS[f] || f).join(', ')}`);
    }
    if (state.requireRealPermitHistory) parts.push('real permit history only');
    if (state.yearBuiltMin != null || state.yearBuiltMax != null) {
      parts.push(`Built ${state.yearBuiltMin ?? 'any'}–${state.yearBuiltMax ?? 'any'}`);
    }
    if (state.canopyMin != null || state.canopyMax != null) {
      parts.push(`Canopy ${state.canopyMin ?? 'any'}–${state.canopyMax ?? 'any'}%`);
    }
    if (state.jobSizePctMin != null || state.jobSizePctMax != null) {
      parts.push(`Job size pct ${state.jobSizePctMin ?? 'any'}–${state.jobSizePctMax ?? 'any'}`);
    }
    return parts.length ? parts.join(' · ') : 'No filters active';
  }

  function renderResults() {
    // Filter FIRST, then rank the filtered subset twice -- once at the
    // current weights (drives both display order and the #1..#N shown
    // on each row), once at Darren default (the arrow's baseline) --
    // both over the SAME filtered population, so #7 really means
    // "7th among what's visible," and the arrow means "moved within
    // this same visible set," not a leftover global DB rank.
    const filtered = applyFilters(PARCELS, state, SOLD_TOWNS, jobSizeByLeadKey);
    const currentRanked = rankLeads(filtered, state.weights, jobSizeByLeadKey, saleRecencyByLeadKey);
    const defaultRankedSameFilters = rankLeads(filtered, DEFAULT_WEIGHTS, jobSizeByLeadKey, saleRecencyByLeadKey);
    const defaultRankByLeadKey = new Map(defaultRankedSameFilters.map((lead) => [lead.lead_key, lead.rank]));

    el('result-count').textContent = `${filtered.length} leads match current filters`;
    el('filter-summary').textContent = summarizeFilters(state);
    const top = currentRanked.slice(0, state.topN);
    el('results-list').innerHTML = top.map((lead) => leadRowHtml(lead, defaultRankByLeadKey)).join('');
    Array.from(el('results-list').querySelectorAll('.expand-btn')).forEach((btn) => {
      btn.addEventListener('click', () => {
        const detail = el('detail-' + cssSafe(btn.getAttribute('data-key')));
        detail.hidden = !detail.hidden;
      });
    });
  }

  function syncHash() {
    window.location.hash = encodeState(state);
  }

  function renderAll() {
    renderControls();
    renderResults();
    syncHash();
  }

  // Set the Weights/Filters panels' initial open/closed state ONCE, from
  // the viewport width at load (same 480px breakpoint the CSS mobile
  // layout already uses) -- open on desktop, closed on phone so the
  // results list is the first thing a crew sees on a small screen.
  // Deliberately not re-evaluated on resize or on every render: that
  // would fight a viewer's own manual expand/collapse click.
  function initPanelOpenState() {
    const isDesktop = window.innerWidth > 480;
    el('weights-details').open = isDesktop;
    el('filters-details').open = isDesktop;
  }

  function renderTagline() {
    el('tagline').textContent = (DATA.metadata && DATA.metadata.tagline) || '';
  }

  // Static, set once -- `sample_size`/`population_size` describe the
  // WHOLE embedded dataset (e.g. teaser builds: top 250 of the share
  // population), not something that changes as a viewer filters within
  // it. `#result-count` (re-rendered on every filter/weight change)
  // still shows the live "N leads match current filters" count among
  // whatever sample is loaded.
  function renderSampleBanner() {
    const meta = DATA.metadata || {};
    el('sample-banner').textContent =
      meta.sample_size && meta.population_size
        ? `Showing a sample of ${meta.sample_size} of ${meta.population_size} leads`
        : '';
  }

  // Hide an entire filter section (not just its individual chips) when
  // there's nothing real to filter on -- a teaser build strips siding_
  // families/roof_family entirely, so materialsOf/roofCoverOf fall back
  // to the single 'Unknown' bucket for every row; a lone "Unknown (250)"
  // chip that can't narrow anything is worse than no filter at all.
  function hideEmptyMaterialSections() {
    if (ALL_SIDING_MATERIALS.length <= 1) el('siding-material-section').style.display = 'none';
    if (ALL_ROOF_MATERIALS.length <= 1) el('roof-cover-section').style.display = 'none';
  }

  initPanelOpenState();
  renderTagline();
  renderSampleBanner();
  hideEmptyMaterialSections();
  bindStaticControls();
  renderAll();
})();

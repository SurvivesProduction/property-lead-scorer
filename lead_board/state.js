/*
 * Shareable-state encode/decode for the interactive slider Lead Board --
 * every slider/filter/toggle value round-trips through the URL hash, so
 * sending a crew's own URL reproduces exactly what they were looking at.
 *
 * Plain CommonJS, no dependencies. Encoding is base64(JSON) of a plain
 * object (not a hand-rolled compact query string) -- this board's state
 * is small (a handful of weights/filters/booleans, never per-lead data),
 * so a readable, trivially-versioned JSON shape was chosen over a denser
 * encoding that would need its own versioning scheme to ever change.
 */
'use strict';

// Every filter-state field that is a `Set` in memory (vs. a plain array
// once serialized through JSON, which has no `Set` type) -- named
// explicitly rather than type-sniffed, so `decodeState` knows exactly
// which array fields to rehydrate back into `Set`s. Keep in sync with
// `filters.js`'s `DEFAULT_FILTER_STATE` whenever a new Set-valued filter
// is added (`sidingMaterials`/`roofCoverMaterials` added 2026-10-29
// alongside those two filters).
const SET_FIELDS = ['towns', 'sidingMaterials', 'roofCoverMaterials'];

function toSerializable(state) {
  const serializable = Object.assign({}, state);
  for (const field of SET_FIELDS) {
    serializable[field] = state[field] ? Array.from(state[field]).sort() : null;
  }
  return serializable;
}

/**
 * `state` -> a URL-hash-safe string (no `#`, already base64url-encoded).
 * Every `SET_FIELDS` entry is serialized as a sorted array for a stable,
 * diffable encoding -- insertion order in a `Set` would otherwise make
 * two functionally-identical states encode differently.
 */
function encodeState(state) {
  const json = JSON.stringify(toSerializable(state));
  return base64UrlEncode(json);
}

/**
 * The inverse of `encodeState` -- returns `null` (never throws) for a
 * hash that isn't valid base64/JSON, so a corrupted or hand-edited URL
 * degrades to "use the defaults" rather than a crash. Every `SET_FIELDS`
 * entry is restored to a `Set` (the shape every other function in this
 * module expects), matching `DEFAULT_FILTER_STATE`'s own `null`-or-`Set`
 * convention in `filters.js`.
 */
function decodeState(hash) {
  try {
    const json = base64UrlDecode(hash);
    const parsed = JSON.parse(json);
    for (const field of SET_FIELDS) {
      if (parsed[field]) {
        parsed[field] = new Set(parsed[field]);
      }
    }
    return parsed;
  } catch (err) {
    return null;
  }
}

function base64UrlEncode(str) {
  const base64 =
    typeof Buffer !== 'undefined'
      ? Buffer.from(str, 'utf-8').toString('base64')
      : btoa(unescape(encodeURIComponent(str)));
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(encoded) {
  let base64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) base64 += '=';
  return typeof Buffer !== 'undefined'
    ? Buffer.from(base64, 'base64').toString('utf-8')
    : decodeURIComponent(escape(atob(base64)));
}

/**
 * The plain-JSON payload the page's "Copy settings" button copies to the
 * clipboard -- deliberately the SAME serializable shape `encodeState`
 * hashes (not a prettified subset), so what Darren pastes into a message
 * is exactly reconstructible, byte-for-byte, from `decodeState` too.
 */
function settingsToClipboardJson(state) {
  return JSON.stringify(toSerializable(state), null, 2);
}

if (typeof module !== 'undefined') {
  module.exports = { encodeState, decodeState, settingsToClipboardJson };
}

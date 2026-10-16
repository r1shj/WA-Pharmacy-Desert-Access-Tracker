/**
 * Shortage Context Map (Day 8). Reports NATIONAL shortage context and a
 * community vulnerability score - never a claim that a specific
 * pharmacy or block group currently lacks a drug. That's why shortages
 * are never plotted as map points: they have no sub-state location to
 * plot. They're shown as a browsable list; only the vulnerability
 * choropleth (built from Day 6's already-geographic access/income data)
 * varies by location.
 */

// Continuous sequential blue ramp over the 0-100 score (DECISIONS.md
// 2026-10-16). Fill used to come from the low/medium/high band, but the
// band can never change with shortage points - see LIMITATIONS.md. The
// old band colors stay as anchors at the band cutoffs.
const VULNERABILITY_RAMP = [
  [0, '#d6e6f9'],
  [33, '#86b6ef'],
  [66, '#2a78d6'],
  [100, '#104281'],
];
const SUPPRESSED_STYLE = { fillColor: '#898781', fillOpacity: 0.35, color: '#898781', weight: 1, dashArray: '3,3' };
const DEFAULT_STYLE = { fillColor: '#e1e0d9', fillOpacity: 0.2, color: '#c3c2b7', weight: 0.5 };

// Interpolate in OKLab, not sRGB, so mid-tones stay clean blue and equal
// score steps look about equally different.
function hexToOklab(hex) {
  const lin = [1, 3, 5].map(i => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  const [r, g, b] = lin;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
  ];
}

function oklabToHex([L, A, B]) {
  const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
  const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
  const s = Math.pow(L - 0.0894841775 * A - 1.2914855480 * B, 3);
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
  return '#' + lin.map(c => {
    const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    return Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0');
  }).join('');
}

const RAMP_LAB = VULNERABILITY_RAMP.map(([stop, hex]) => [stop, hexToOklab(hex)]);

function colorForScore(score) {
  const x = Math.min(100, Math.max(0, score));
  for (let i = 1; i < RAMP_LAB.length; i++) {
    const [s0, c0] = RAMP_LAB[i - 1];
    const [s1, c1] = RAMP_LAB[i];
    if (x <= s1) {
      const t = (x - s0) / (s1 - s0);
      return oklabToHex(c0.map((v, k) => v + t * (c1[k] - v)));
    }
  }
  return VULNERABILITY_RAMP[VULNERABILITY_RAMP.length - 1][1];
}

function styleForScore(s) {
  if (s.vulnerability_score_basis === 'partial_income_suppressed') return SUPPRESSED_STYLE;
  const color = colorForScore(s.vulnerability_score);
  return { fillColor: color, fillOpacity: 0.6, color: color, weight: 0.5 };
}

// Legend gradient from the same function as the fill, so they can't drift.
// Guarded: a page from an older deploy (no gradient bar) must not stop the
// rest of this script and leave the map blank.
const gradientEl = document.getElementById('vulnerability-gradient');
if (gradientEl) {
  gradientEl.style.background =
    `linear-gradient(to right, ${Array.from({ length: 11 }, (_, i) => colorForScore(i * 10)).join(', ')})`;
}

function popupHtmlForScore(s) {
  if (s.vulnerability_score_basis === 'partial_income_suppressed') {
    return `
      <strong>Block group ${s.geoid}</strong><br>
      <span class="popup__row" style="font-weight:600; color:#ab7900">⚠ Partial score - income data suppressed</span><br>
      <span class="popup__row">Score: ${s.vulnerability_score} / ${s.vulnerability_score_max} (access + shortage only)</span><br>
      <span class="popup__row">Low pharmacy access: ${s.is_low_access ? 'yes' : 'no'}</span><br>
      <span class="popup__row">Nearest pharmacy: ${s.nearest_pharmacy_miles != null ? s.nearest_pharmacy_miles.toFixed(2) + ' mi' : 'n/a'}</span>
    `;
  }
  return `
    <strong>Block group ${s.geoid}</strong><br>
    <span class="popup__row">Vulnerability: <strong>${s.vulnerability_band}</strong> (${s.vulnerability_score} / ${s.vulnerability_score_max})</span><br>
    <span class="popup__row">Low pharmacy access: ${s.is_low_access ? 'yes' : 'no'} (${s.nearest_pharmacy_miles != null ? s.nearest_pharmacy_miles.toFixed(2) + ' mi to nearest' : 'n/a'})</span><br>
    <span class="popup__row">Income: ${s.income_status}</span><br>
    <span class="popup__row">Desert status: ${s.pharmacy_desert_status}</span>
  `;
}

const map = L.map('map').setView([47.4, -120.6], 7);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

window.addEventListener('load', () => map.invalidateSize());
setTimeout(() => map.invalidateSize(), 150);
window.addEventListener('resize', () => map.invalidateSize());

const blockGroupLayersByGeoid = {};

function reportLayerError(what) {
  const message = `Couldn't load ${what}. Reload the page to try again.`;
  const el = document.getElementById('layer-error');
  if (!el) { console.warn(message); return; }  // page from an older deploy
  el.hidden = false;
  el.textContent = message;
}

function loadBlockGroupGeometry() {
  return fetchJSON('/api/shortages/block-group-geometry')
    .then(geojson => {
      L.geoJSON(geojson, {
        style: () => DEFAULT_STYLE,
        onEachFeature: (f, layer) => {
          blockGroupLayersByGeoid[f.properties.geoid] = layer;
        },
      }).addTo(map);
    });
}

// --- Date-dependent content: choropleth colors and popups, the summary
// line, the shortage count and list. Both requests must succeed before any
// of it is shown, and it's loaded, shown and cleared only through
// DateSlider - so it always matches the date in the slider readout.

function loadShortageDate(dateStr, signal) {
  return Promise.all([
    fetchJSON(`/api/shortages/vulnerability-scores?date=${dateStr}`, signal),
    fetchJSON(`/api/shortages/active?date=${dateStr}`, signal),
  ]).then(([vulnerability, active]) => ({ vulnerability, active }));
}

function renderShortageDate({ vulnerability, active }, dateStr) {
  if (vulnerability.as_of_date !== dateStr || active.as_of_date !== dateStr) {
    throw new Error(`asked for ${dateStr}, got ${vulnerability.as_of_date} / ${active.as_of_date}`);
  }
  vulnerability.scores.forEach(s => {
    const layer = blockGroupLayersByGeoid[s.geoid];
    if (!layer) return;
    layer.setStyle(styleForScore(s));
    layer.bindPopup(popupHtmlForScore(s));
  });
  document.getElementById('shortage-summary').innerHTML = `
    <strong>${vulnerability.active_chronic_shortage_count}</strong> active shortages as of ${vulnerability.as_of_date}
    in the 7 tracked chronic-condition categories -&gt; contributes
    <strong>${vulnerability.shortage_points}/${vulnerability.shortage_points_max}</strong> points to every block group's
    vulnerability score (a single statewide number; shortage data has no
    sub-state geography, so this cannot vary by location).
  `;

  document.getElementById('shortage-count').textContent = active.count;
  const listEl = document.getElementById('shortage-list');
  listEl.innerHTML = '';
  active.shortages.forEach(s => {
    const item = document.createElement('div');
    item.className = 'shortage-item';
    const badge = s.counts_toward_vulnerability
      ? '<span class="chronic-badge" title="Counts toward the vulnerability index\'s shortage component">chronic</span>'
      : '';
    // An end date means two different things - never call a feed
    // dropout "resolved" (see DECISIONS.md 2026-10-15).
    let duration;
    if (s.end_date_basis === 'confirmed_resolved') {
      duration = `resolved ${s.end_date}`;
    } else if (s.end_date_basis === 'last_observed_in_feed') {
      duration = `last listed by FDA ${s.end_date} (left the feed - not confirmed resolved)`;
    } else {
      duration = `active since ${s.start_date} (open-ended)`;
    }
    item.innerHTML = `
      <div class="shortage-item__name">${s.generic_name}${badge}</div>
      <div class="shortage-item__meta">${s.therapeutic_category || 'Uncategorized'}</div>
      <div class="shortage-item__meta">${s.source_status} · ${duration}</div>
    `;
    listEl.appendChild(item);
  });
}

function clearShortageDate() {
  map.closePopup();
  Object.values(blockGroupLayersByGeoid).forEach(layer => {
    layer.setStyle(DEFAULT_STYLE);
    layer.unbindPopup();
  });
  document.getElementById('shortage-summary').innerHTML = '';
  document.getElementById('shortage-count').textContent = '–';
  document.getElementById('shortage-list').innerHTML = '';
}

// Geometry must be in place (blockGroupLayersByGeoid populated) before
// the slider's first load, or every setStyle() call finds no matching
// layer and silently no-ops - sequence explicitly rather than firing both
// fetches in parallel and hoping the timing works out.
Promise.all([
  loadBlockGroupGeometry(),
  fetchJSON('/api/shortages/config'),
]).then(([_, cfg]) => {
  document.getElementById('interval-note').innerHTML = `
    <strong>${cfg.open_ended_count} of ${cfg.total_count} shortages have open-ended, unconfirmed end dates.</strong>
    These show as "active since [date]," not a confirmed start-to-finish duration — openFDA has no
    field marking when most shortages end, only when FDA first posted the notice.
    ${cfg.confirmed_resolved_count} have a confirmed resolution date. Since daily observation began
    (${cfg.daily_observation_since}), ${cfg.dropped_from_feed_count} more have left FDA's feed without
    ever being marked resolved — nearly all were discontinuation notices leaving the list about a year
    after posting, so they're shown as "last listed," never as resolved.
    Data does not exist before 2012 in this dataset — the slider is bounded to that range.
  `;
  new DateSlider({
    container: document.getElementById('slider-root'),
    minDate: cfg.slider_min_date,
    maxDate: cfg.slider_max_date,
    initialDate: cfg.slider_max_date,
    markers: [{ date: cfg.slider_min_date, label: 'Earliest data in this dataset' }],
    load: loadShortageDate,
    render: renderShortageDate,
    clear: clearShortageDate,
  });
}).catch(() => reportLayerError('the map (block-group shapes or date range), so the date slider is unavailable'));

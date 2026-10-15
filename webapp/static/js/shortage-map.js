/**
 * Shortage Context Map (Day 8). Reports NATIONAL shortage context and a
 * community vulnerability score - never a claim that a specific
 * pharmacy or block group currently lacks a drug. That's why shortages
 * are never plotted as map points: they have no sub-state location to
 * plot. They're shown as a browsable list; only the vulnerability
 * choropleth (built from Day 6's already-geographic access/income data)
 * varies by location.
 */

// Sequential blue ramp (dataviz skill's default sequential hue) -
// vulnerability is a magnitude/severity scale, not independent
// categories, so it gets a light->dark ramp rather than status colors.
const VULNERABILITY_COLORS = {
  low: '#86b6ef',
  medium: '#2a78d6',
  high: '#104281',
};
const SUPPRESSED_STYLE = { fillColor: '#898781', fillOpacity: 0.35, color: '#898781', weight: 1, dashArray: '3,3' };
const DEFAULT_STYLE = { fillColor: '#e1e0d9', fillOpacity: 0.2, color: '#c3c2b7', weight: 0.5 };

function styleForScore(s) {
  if (s.vulnerability_score_basis === 'partial_income_suppressed') return SUPPRESSED_STYLE;
  const color = VULNERABILITY_COLORS[s.vulnerability_band] || '#c3c2b7';
  return { fillColor: color, fillOpacity: 0.6, color: color, weight: 0.5 };
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

function loadBlockGroupGeometry() {
  return fetch('/api/shortages/block-group-geometry')
    .then(r => r.json())
    .then(geojson => {
      L.geoJSON(geojson, {
        style: () => DEFAULT_STYLE,
        onEachFeature: (f, layer) => {
          blockGroupLayersByGeoid[f.properties.geoid] = layer;
        },
      }).addTo(map);
    });
}

function updateVulnerability(date) {
  fetch(`/api/shortages/vulnerability-scores?date=${date}`)
    .then(r => r.json())
    .then(data => {
      data.scores.forEach(s => {
        const layer = blockGroupLayersByGeoid[s.geoid];
        if (!layer) return;
        layer.setStyle(styleForScore(s));
        layer.bindPopup(popupHtmlForScore(s));
      });
      document.getElementById('shortage-summary').innerHTML = `
        <strong>${data.active_chronic_shortage_count}</strong> active shortages as of ${data.as_of_date}
        in the 7 tracked chronic-condition categories -&gt; contributes
        <strong>${data.shortage_points}/${data.shortage_points_max}</strong> points to every block group's
        vulnerability score (a single statewide number; shortage data has no
        sub-state geography, so this cannot vary by location).
      `;
    });
}

function updateShortageList(date) {
  fetch(`/api/shortages/active?date=${date}`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('shortage-count').textContent = data.count;
      const listEl = document.getElementById('shortage-list');
      listEl.innerHTML = '';
      data.shortages.forEach(s => {
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
    });
}

// Geometry must be in place (blockGroupLayersByGeoid populated) before
// the first updateVulnerability() call, or every setStyle() call finds
// no matching layer and silently no-ops - sequence explicitly rather
// than firing both fetches in parallel and hoping the timing works out.
Promise.all([
  loadBlockGroupGeometry(),
  fetch('/api/shortages/config').then(r => r.json()),
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
    onChange: (dateStr) => {
      updateVulnerability(dateStr);
      updateShortageList(dateStr);
    },
  });
  updateVulnerability(cfg.slider_max_date);
  updateShortageList(cfg.slider_max_date);
});

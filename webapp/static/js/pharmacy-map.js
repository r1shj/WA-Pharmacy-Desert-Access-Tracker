const OWNERSHIP_COLORS = {
  chain: '#2a78d6',
  health_system: '#1baf7a',
  government_or_tribal: '#eda100',
  independent_confirmed: '#008300',
  unknown: '#898781',
};

const DESERT_STYLE = {
  desert: { fillColor: '#d03b3b', fillOpacity: 0.55, color: '#d03b3b', weight: 0.5 },
  indeterminate_income_suppressed: { fillColor: '#fab219', fillOpacity: 0.5, color: '#fab219', weight: 0.5 },
  not_desert: { fillColor: '#e1e0d9', fillOpacity: 0.25, color: '#c3c2b7', weight: 0.5 },
};

// Reuses the dataviz skill's reserved "warning" status color for the
// stroke - review_only locations carry ownership-category fill (still
// informative) but a warning ring flags "not yet confirmed as a walk-in
// access point," per the standing project rule to carry REVIEW records
// forward with their flag rather than drop or silently blend them in.
const REVIEW_ONLY_STROKE = '#fab219';
const CONFIRMED_STROKE = '#ffffff';

const map = L.map('map').setView([47.4, -120.6], 7);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

// Keep Leaflet's idea of the map size in sync with its container. Leaflet
// measures once at init, but the container's height changes afterwards -
// the slider, notes and counts below the map fill in as data loads, and
// the window can resize - and a stale size left the map off-center and
// stopped popups auto-panning into view (DECISIONS.md 2026-10-16).
new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById('map'));

let pharmacyLayer = null;

function popupHtml(props) {
  const pharmacies = props.pharmacies || [];
  const rows = pharmacies.map(p => {
    const isReview = p.walk_in_access === 'unknown';
    const flag = isReview
      ? '<div class="popup__row" style="color:#ab7900; font-weight:600">⚠ Needs manual review — inclusion as a walk-in access point not yet confirmed</div>'
      : '';
    return `
    <div style="margin-top:6px; padding-top:6px; border-top:1px solid var(--gridline)">
      <div class="popup__title">${p.organization_name}${p.dba_name ? ' — ' + p.dba_name : ''}</div>
      <div class="popup__row">Ownership: ${p.ownership_category}${p.parent_organization ? ' (' + p.parent_organization + ')' : ''}</div>
      <div class="popup__row">Type: ${p.pharmacy_type}</div>
      ${flag}
    </div>`;
  }).join('');
  const headerFlag = props.review_only
    ? '<div class="popup__row" style="color:#ab7900; font-weight:600; margin-top:2px">⚠ All pharmacies at this location are in the REVIEW bucket</div>'
    : '';
  return `<div><strong>${props.address_1}, ${props.city}</strong>${headerFlag}${rows}</div>`;
}

// Static layers (not date-dependent). A failure is reported, never silent.
function reportLayerError(what) {
  const message = `Couldn't load ${what}. Reload the page to try again.`;
  const el = document.getElementById('layer-error');
  if (!el) { console.warn(message); return; }  // page from an older deploy
  el.hidden = false;
  el.textContent = message;
}

function loadBlockGroups() {
  fetchJSON('/api/pharmacy/block-groups')
    .then(geojson => {
      L.geoJSON(geojson, {
        style: f => DESERT_STYLE[f.properties.pharmacy_desert_status] || DESERT_STYLE.not_desert,
        onEachFeature: (f, layer) => {
          const p = f.properties;
          layer.bindPopup(`
            <strong>Block group ${p.geoid}</strong><br>
            Status: ${p.pharmacy_desert_status}<br>
            ${p.is_urban ? 'Urban' : 'Rural'} (threshold ${p.distance_threshold_miles}mi)<br>
            Nearest confirmed walk-in pharmacy: ${p.nearest_pharmacy_miles != null ? p.nearest_pharmacy_miles.toFixed(2) + ' mi (straight line)' : 'n/a'}<br>
            Income: ${p.income_status}<br>
            Population: ${p.population}
          `);
        },
      }).addTo(map);
      // Desert polygons must stay under the pharmacy points.
      if (pharmacyLayer) pharmacyLayer.bringToFront();
    })
    .catch(() => reportLayerError('the pharmacy desert layer'));
}

function loadBorderPharmacies() {
  fetchJSON('/api/pharmacy/border-pharmacies')
    .then(geojson => {
      L.geoJSON(geojson, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: 5,
          color: '#898781',
          weight: 1.5,
          fillOpacity: 0,
        }),
        onEachFeature: (f, layer) => {
          const p = f.properties;
          layer.bindPopup(`
            <strong>${p.organization_name}${p.dba_name ? ' — ' + p.dba_name : ''}</strong><br>
            <span class="popup__row">${p.address_1}, ${p.city}, ${p.state}</span><br>
            <span class="popup__row" style="font-style:italic">Reference only — not part of the WA pharmacy dataset (no ownership/dedup classification applied)</span>
          `);
        },
      }).addTo(map);
    })
    .catch(() => reportLayerError('the Oregon/Idaho border pharmacies'));
}

// --- Date-dependent content: the points, their count, and the mode note.
// Loaded, shown and cleared only through DateSlider, so they always match
// the date in the slider readout.

function loadPharmaciesForDate(dateStr, signal) {
  return fetchJSON(`/api/pharmacy/pharmacies?date=${dateStr}`, signal);
}

function renderPharmacies(geojson, dateStr) {
  if (geojson.as_of_date !== dateStr) {
    throw new Error(`asked for ${dateStr}, got ${geojson.as_of_date}`);
  }
  clearPharmacies();
  pharmacyLayer = L.geoJSON(geojson, {
    pointToLayer: (f, latlng) => L.circleMarker(latlng, {
      radius: f.properties.review_only ? 6 : 5,
      color: f.properties.review_only ? REVIEW_ONLY_STROKE : CONFIRMED_STROKE,
      weight: f.properties.review_only ? 2 : 1,
      dashArray: f.properties.review_only ? '2,2' : null,
      fillColor: OWNERSHIP_COLORS[f.properties.ownership_category] || OWNERSHIP_COLORS.unknown,
      fillOpacity: f.properties.review_only ? 0.7 : 0.9,
    }),
    onEachFeature: (f, layer) => layer.bindPopup(popupHtml(f.properties)),
  }).addTo(map);
  document.getElementById('pharmacy-count').textContent = geojson.features.length;
  document.getElementById('mode-note').innerHTML = modeNoteHtml(geojson);
}

function clearPharmacies() {
  map.closePopup();
  if (pharmacyLayer) { map.removeLayer(pharmacyLayer); pharmacyLayer = null; }
  document.getElementById('pharmacy-count').textContent = '–';
  document.getElementById('mode-note').innerHTML = '';
}

// Driven by what the API actually used for this date, not re-derived
// here, so the note can't disagree with the points on the map.
function modeNoteHtml(geojson) {
  const dateStr = geojson.as_of_date;
  if (geojson.basis === 'observed' && geojson.observed_date === dateStr) {
    return `<span class="limitation-note--mode">Observed snapshot</span> — the federal NPI registry as swept on ${dateStr}, not reconstructed.`;
  } else if (geojson.basis === 'observed') {
    return `<span class="limitation-note--mode">Most recent observed snapshot (${geojson.observed_date})</span> — the registry wasn't swept on ${dateStr}, so this shows the last real observation before it.`;
  }
  return `<span class="limitation-note--mode">Backfilled estimate</span> — based on when each pharmacy's federal registration (NPI) was first recorded, not a direct observation of ${dateStr}. It can show openings but not closures.`;
}

fetchJSON('/api/pharmacy/config')
  .then(cfg => {
    new DateSlider({
      container: document.getElementById('slider-root'),
      minDate: cfg.slider_min_date,
      maxDate: cfg.slider_max_date,
      initialDate: cfg.slider_max_date,
      // One marker for where daily observation begins - a tick per
      // observed day would bury the slider within a few weeks.
      markers: [{ date: cfg.last_backfilled_date, label: 'Last backfilled date' }]
        .concat(cfg.first_observed_date ? [{ date: cfg.first_observed_date, label: 'First observed registry snapshot' }] : []),
      load: loadPharmaciesForDate,
      render: renderPharmacies,
      clear: clearPharmacies,
    });
  })
  .catch(() => reportLayerError("the map's date range, so the date slider is unavailable"));

loadBlockGroups();
loadBorderPharmacies();

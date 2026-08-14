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

// Leaflet reads its container's size at init time; inside a flex layout
// that size isn't always resolved yet on first paint.
window.addEventListener('load', () => map.invalidateSize());
setTimeout(() => map.invalidateSize(), 150);
window.addEventListener('resize', () => map.invalidateSize());

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

function loadBlockGroups() {
  fetch('/api/pharmacy/block-groups')
    .then(r => r.json())
    .then(geojson => {
      L.geoJSON(geojson, {
        style: f => DESERT_STYLE[f.properties.pharmacy_desert_status] || DESERT_STYLE.not_desert,
        onEachFeature: (f, layer) => {
          const p = f.properties;
          layer.bindPopup(`
            <strong>Block group ${p.geoid}</strong><br>
            Status: ${p.pharmacy_desert_status}<br>
            ${p.is_urban ? 'Urban' : 'Rural'} (threshold ${p.distance_threshold_miles}mi)<br>
            Nearest pharmacy: ${p.nearest_pharmacy_miles != null ? p.nearest_pharmacy_miles.toFixed(2) + ' mi' : 'n/a'}<br>
            Income: ${p.income_status}<br>
            Population: ${p.population}
          `);
        },
      }).addTo(map);
    });
}

function loadBorderPharmacies() {
  fetch('/api/pharmacy/border-pharmacies')
    .then(r => r.json())
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
    });
}

function loadPharmacies(date) {
  fetch(`/api/pharmacy/pharmacies?date=${date}`)
    .then(r => r.json())
    .then(geojson => {
      if (pharmacyLayer) map.removeLayer(pharmacyLayer);
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
    });
}

function updateModeNote(dateStr, cfg) {
  const noteEl = document.getElementById('mode-note');
  const selected = new Date(dateStr + 'T00:00:00Z');
  const lastBackfilled = new Date(cfg.last_backfilled_date + 'T00:00:00Z');
  const observed = cfg.observed_dates_available;
  const isObservedDate = observed.includes(dateStr);

  let mode;
  if (isObservedDate) {
    mode = `<span class="limitation-note--mode">Observed snapshot</span> — a real daily capture of the dataset on ${dateStr}, not reconstructed.`;
  } else if (selected <= lastBackfilled) {
    mode = `<span class="limitation-note--mode">Backfilled estimate</span> — based on when each pharmacy's federal registration (NPI) was first recorded, not a direct observation of ${dateStr}.`;
  } else {
    mode = `<span class="limitation-note--mode">No snapshot for this exact date yet</span> — showing the most recent available data. Daily granularity only starts accumulating once Day 8's automated loading is running.`;
  }
  noteEl.innerHTML = mode;
}

fetch('/api/pharmacy/config')
  .then(r => r.json())
  .then(cfg => {
    const slider = new DateSlider({
      container: document.getElementById('slider-root'),
      minDate: cfg.slider_min_date,
      maxDate: cfg.slider_max_date,
      initialDate: cfg.slider_max_date,
      markers: [{ date: cfg.last_backfilled_date, label: 'Last backfilled date' }]
        .concat(cfg.observed_dates_available.map(d => ({ date: d, label: 'Observed snapshot' }))),
      onChange: (dateStr) => {
        loadPharmacies(dateStr);
        updateModeNote(dateStr, cfg);
      },
    });
    updateModeNote(slider.getValue(), cfg);
    loadPharmacies(slider.getValue());
  });

loadBlockGroups();
loadBorderPharmacies();

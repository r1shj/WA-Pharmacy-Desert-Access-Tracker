/**
 * Shared date-slider component - used by /map/pharmacy (Day 7) and
 * /map/shortages (Day 8). Not hardcoded to either dataset: it owns the
 * slider, the date readout, and the whole load cycle for a date, and calls
 * back into the page for the dataset-specific parts.
 *
 * The one rule it enforces for both maps (DECISIONS.md 2026-10-16): the
 * date in the readout and everything date-dependent on the page always
 * agree. As soon as the date changes, `clear` removes the old date's
 * content; `render` only ever receives data for the date currently shown;
 * a failure leaves the content cleared and says so.
 *
 * - Debounced: while dragging, data is fetched only after a short pause,
 *   and immediately on release - not once per pixel of drag.
 * - In-flight requests for an abandoned date are aborted, and a response
 *   that arrives late for an old date is discarded.
 *
 * Usage:
 *   const slider = new DateSlider({
 *     container: document.getElementById('slider-root'),
 *     minDate: '2005-05-24',
 *     maxDate: '2026-07-19',
 *     initialDate: '2026-07-19',
 *     markers: [{ date: '2026-06-30', label: 'Last backfilled date' }],
 *     load: (dateStr, signal) => Promise<data>,   // fetch everything for the date
 *     render: (data, dateStr) => { ... },         // show it
 *     clear: (dateStr) => { ... },                // remove date-dependent content
 *   });
 */

// fetch() that rejects on any non-2xx response or non-JSON body, so a
// server error can never be half-parsed into the page.
async function fetchJSON(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`${url} returned HTTP ${response.status}`);
  }
  return response.json();
}

class DateSlider {
  constructor({ container, minDate, maxDate, initialDate, markers = [], load, render, clear, debounceMs = 250 }) {
    this.container = container;
    this.minDate = new Date(minDate + 'T00:00:00Z');
    this.maxDate = new Date(maxDate + 'T00:00:00Z');
    this.initialDate = new Date((initialDate || maxDate) + 'T00:00:00Z');
    this.markers = markers;
    this.loadFn = load;
    this.renderFn = render;
    this.clearFn = clear;
    this.debounceMs = debounceMs;
    this.totalDays = Math.round((this.maxDate - this.minDate) / 86400000);

    this._requestSeq = 0;      // bumps on every new target date
    this._inFlight = null;     // AbortController for the current request
    this._debounceTimer = null;
    this._shownDate = null;    // date whose data is on the page, if any
    this._render();
    this._requestDate(this.getValue(), { immediate: true });
  }

  _dateToOffset(date) {
    return Math.round((date - this.minDate) / 86400000);
  }

  _offsetToDateString(offset) {
    const d = new Date(this.minDate.getTime() + offset * 86400000);
    return d.toISOString().slice(0, 10);
  }

  _render() {
    const initialOffset = this._dateToOffset(this.initialDate);
    this.container.innerHTML = `
      <div class="date-slider">
        <input type="range" class="date-slider__range" min="0" max="${this.totalDays}" value="${initialOffset}" step="1"
               aria-label="Date">
        <div class="date-slider__markers"></div>
        <div class="date-slider__readout"></div>
      </div>
      <div class="date-slider__status" role="status" aria-live="polite"></div>
    `;
    this.rangeEl = this.container.querySelector('.date-slider__range');
    this.readoutEl = this.container.querySelector('.date-slider__readout');
    this.markersEl = this.container.querySelector('.date-slider__markers');
    this.statusEl = this.container.querySelector('.date-slider__status');

    this.markers.forEach(m => {
      const offset = this._dateToOffset(new Date(m.date + 'T00:00:00Z'));
      const pct = (offset / this.totalDays) * 100;
      const tick = document.createElement('div');
      tick.className = 'date-slider__marker';
      tick.style.left = pct + '%';
      tick.title = `${m.label} (${m.date})`;
      this.markersEl.appendChild(tick);
    });

    // 'input' fires continuously while dragging; 'change' fires on release
    // (and on each keyboard step).
    this.rangeEl.addEventListener('input', () => this._requestDate(this.getValue(), { immediate: false }));
    this.rangeEl.addEventListener('change', () => this._requestDate(this.getValue(), { immediate: true }));
    this.statusEl.addEventListener('click', (e) => {
      if (e.target.closest('.date-slider__retry')) this._requestDate(this.getValue(), { immediate: true, force: true });
    });
    this.readoutEl.textContent = this.getValue();
  }

  _setState(state, dateStr) {
    this.container.dataset.state = state;          // loading | loaded | error
    this.container.dataset.date = dateStr;
    if (state === 'loading') {
      this.statusEl.textContent = `Loading ${dateStr}…`;
    } else if (state === 'error') {
      this.statusEl.innerHTML = `Couldn't load ${dateStr}. <button type="button" class="date-slider__retry">Retry</button>`;
    } else {
      this.statusEl.textContent = '';
    }
  }

  _requestDate(dateStr, { immediate, force = false }) {
    this.readoutEl.textContent = dateStr;
    const sameTarget = dateStr === this._targetDate;
    if (sameTarget && !force && (this._shownDate === dateStr || this._inFlight)) {
      return;  // already showing or already fetching this date
    }

    if (!sameTarget || force) {
      this._targetDate = dateStr;
      this._requestSeq++;
      if (this._inFlight) { this._inFlight.abort(); this._inFlight = null; }
      // Never leave another date's data under this label.
      if (this._shownDate !== null || this.container.dataset.state === 'error') {
        this._shownDate = null;
        if (this.clearFn) this.clearFn(dateStr);
      }
      this._setState('loading', dateStr);
    }

    clearTimeout(this._debounceTimer);
    if (immediate) {
      this._fetch(dateStr, this._requestSeq);
    } else {
      const seq = this._requestSeq;
      this._debounceTimer = setTimeout(() => this._fetch(dateStr, seq), this.debounceMs);
    }
  }

  async _fetch(dateStr, seq) {
    if (seq !== this._requestSeq || this._inFlight) return;
    const controller = new AbortController();
    this._inFlight = controller;
    try {
      const data = await this.loadFn(dateStr, controller.signal);
      if (seq !== this._requestSeq) return;        // a newer date was chosen meanwhile
      this.renderFn(data, dateStr);
      this._shownDate = dateStr;
      this._setState('loaded', dateStr);
    } catch (err) {
      if (seq !== this._requestSeq || err.name === 'AbortError') return;
      console.warn(`Date ${dateStr} failed to load:`, err);
      if (this.clearFn) this.clearFn(dateStr);
      this._setState('error', dateStr);
    } finally {
      if (this._inFlight === controller) this._inFlight = null;
    }
  }

  getValue() {
    return this._offsetToDateString(parseInt(this.rangeEl.value, 10));
  }

  setValue(dateStr) {
    const offset = this._dateToOffset(new Date(dateStr + 'T00:00:00Z'));
    this.rangeEl.value = offset;
    this._requestDate(this.getValue(), { immediate: true });
  }
}

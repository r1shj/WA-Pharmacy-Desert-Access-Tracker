/**
 * Shared date-slider component - used by /map/pharmacy (Day 7) and
 * /map/shortages (Day 8). Not hardcoded to either dataset: takes a date
 * range and a callback, nothing dataset-specific.
 *
 * Usage:
 *   const slider = new DateSlider({
 *     container: document.getElementById('slider-root'),
 *     minDate: '2005-05-24',
 *     maxDate: '2026-07-19',
 *     initialDate: '2026-07-19',
 *     markers: [{ date: '2026-06-30', label: 'Last backfilled date' }],
 *     onChange: (dateStr) => { ... },
 *   });
 */
class DateSlider {
  constructor({ container, minDate, maxDate, initialDate, markers = [], onChange }) {
    this.container = container;
    this.minDate = new Date(minDate + 'T00:00:00Z');
    this.maxDate = new Date(maxDate + 'T00:00:00Z');
    this.initialDate = new Date((initialDate || maxDate) + 'T00:00:00Z');
    this.markers = markers;
    this.onChange = onChange;
    this.totalDays = Math.round((this.maxDate - this.minDate) / 86400000);
    this._render();
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
        <input type="range" class="date-slider__range" min="0" max="${this.totalDays}" value="${initialOffset}" step="1">
        <div class="date-slider__markers"></div>
        <div class="date-slider__readout"></div>
      </div>
    `;
    this.rangeEl = this.container.querySelector('.date-slider__range');
    this.readoutEl = this.container.querySelector('.date-slider__readout');
    this.markersEl = this.container.querySelector('.date-slider__markers');

    this.markers.forEach(m => {
      const offset = this._dateToOffset(new Date(m.date + 'T00:00:00Z'));
      const pct = (offset / this.totalDays) * 100;
      const tick = document.createElement('div');
      tick.className = 'date-slider__marker';
      tick.style.left = pct + '%';
      tick.title = `${m.label} (${m.date})`;
      this.markersEl.appendChild(tick);
    });

    this.rangeEl.addEventListener('input', () => this._handleChange());
    this._updateReadout(initialOffset);
  }

  _updateReadout(offset) {
    this.readoutEl.textContent = this._offsetToDateString(offset);
  }

  _handleChange() {
    const offset = parseInt(this.rangeEl.value, 10);
    this._updateReadout(offset);
    if (this.onChange) this.onChange(this._offsetToDateString(offset));
  }

  getValue() {
    return this._offsetToDateString(parseInt(this.rangeEl.value, 10));
  }

  setValue(dateStr) {
    const offset = this._dateToOffset(new Date(dateStr + 'T00:00:00Z'));
    this.rangeEl.value = offset;
    this._updateReadout(offset);
  }
}

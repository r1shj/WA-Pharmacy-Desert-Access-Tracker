/**
 * Shared map gestures for /map/pharmacy and /map/shortages
 * (DECISIONS.md 2026-10-18). The map pages scroll like a normal page, so
 * the map must not trap the scroll:
 *
 * - Mouse wheel / trackpad scroll over the map scrolls the page. Ctrl or
 *   Cmd + wheel zooms the map - and so does a trackpad pinch, which the
 *   browser reports as Ctrl + wheel. Mouse drag and the +/- buttons work
 *   as before.
 * - On touch-first devices (phones, tablets) one finger scrolls the page
 *   and two fingers pan and zoom the map. This is Leaflet's own two-finger
 *   handler with one-finger dragging turned off; Leaflet's CSS then lets
 *   the browser scroll the page (touch-action: pan-x pan-y).
 *
 * A short on-map hint explains this when the scroll goes to the page.
 * Plain Leaflet 1.9, no plugin.
 *
 * Usage: makeMapScrollFriendly(map) once, right after creating the map.
 */
function makeMapScrollFriendly(map) {
  const container = map.getContainer();
  const hint = L.DomUtil.create('div', 'map-gesture-hint', container);
  hint.setAttribute('aria-hidden', 'true');
  let hideTimer = null;
  const showHint = (text, ms) => {
    hint.textContent = text;
    hint.classList.add('is-visible');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => hint.classList.remove('is-visible'), ms);
  };
  const hideHint = () => { clearTimeout(hideTimer); hint.classList.remove('is-visible'); };

  // Wheel: Leaflet's wheel-zoom listener sits on the map container. This
  // capture-phase listener runs first and stops every wheel event without
  // Ctrl/Cmd from reaching it; nothing cancels those events, so the
  // browser scrolls the page as it would anywhere else.
  const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform);
  const wheelHint = `Use ${isMac ? '⌘' : 'Ctrl'} + scroll to zoom the map`;
  container.addEventListener('wheel', (e) => {
    if (e.ctrlKey || e.metaKey) { hideHint(); return; }
    e.stopPropagation();
    showHint(wheelHint, 1500);
  }, { capture: true, passive: true });

  // Touch: one-finger dragging off on touch-first devices, kept on for a
  // mouse. Re-checked if the primary input changes (e.g. a tablet docked
  // to a keyboard and trackpad).
  const touchFirst = window.matchMedia('(pointer: coarse)');
  const applyInputMode = () => {
    if (touchFirst.matches) map.dragging.disable(); else map.dragging.enable();
  };
  applyInputMode();
  touchFirst.addEventListener('change', applyInputMode);

  // The first one-finger swipe over the map (per page load) scrolls the
  // page and shows how to move the map instead.
  let touchHintShown = false;
  container.addEventListener('touchmove', (e) => {
    if (e.touches.length > 1) { hideHint(); return; }
    if (touchHintShown || map.dragging.enabled()) return;
    touchHintShown = true;
    showHint('Use two fingers to move the map', 2000);
  }, { passive: true });
}

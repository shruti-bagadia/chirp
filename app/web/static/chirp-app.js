/* Chirp dashboard glue: selection, HTMX events, and effects. */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  function updateBar() {
    const n = $$('#queue-form input[name="ids"]:checked').length;
    const go = $('#go'), let_ = $('#letgo');
    if (!go) return;
    go.disabled = let_.disabled = n === 0;
    go.textContent = n ? `Ready to fly ${n}` : 'Ready to fly';
    const all = $('#pick-all');
    const boxes = $$('#queue-form input[name="ids"]');
    if (all) all.checked = boxes.length > 0 && n === boxes.length;
  }

  document.addEventListener('change', e => {
    if (e.target.id === 'pick-all') {
      $$('#queue-form input[name="ids"]').forEach(b => { b.checked = e.target.checked; });
    }
    if (e.target.closest('#queue-form')) updateBar();
  });

  // Animate rows before the bulk request; hx-swap uses a delay so the motion can finish.
  document.addEventListener('htmx:beforeRequest', e => {
    const el = e.detail.elt;
    const action = el.getAttribute && el.getAttribute('data-bulk');
    if (!action) return;
    const cls = action === 'approve' ? 'lift' : 'drop';
    const one = el.dataset.id && document.getElementById('row-' + el.dataset.id);
    if (one) { ChirpFX.closeSheet(); one.classList.add(cls); }
    else $$('#queue-form input[name="ids"]:checked').forEach(b => b.closest('.row').classList.add(cls));
    if (action === 'approve') ChirpFX.fly(); else { ChirpFX.leaves(4); ChirpFX.sound.rustle(); }
  });

  // Server events arrive through the HX-Trigger header.
  document.addEventListener('chirp:toast', e => ChirpFX.toast(e.detail.value || e.detail.message));
  document.addEventListener('chirp:approved', e => ChirpFX.toast(`${e.detail.count} ready to fly! ${e.detail.when || ''}`.trim()));
  document.addEventListener('chirp:rejected', e => ChirpFX.toast(`Let go of ${e.detail.count}. They won't come back.`));
  document.addEventListener('chirp:celebrate', () => { ChirpFX.leaves(14); ChirpFX.sound.flyAway(); });
  document.addEventListener('chirp:close-sheet', () => ChirpFX.closeSheet());

  document.addEventListener('htmx:afterSwap', e => {
    if (e.detail.target.id === 'sheet-body') ChirpFX.openSheet();
    updateBar();
  });

  // Copy buttons in quick apply.
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); } catch (_) { /* clipboard blocked */ }
    const t = b.textContent; b.textContent = 'Copied'; setTimeout(() => { b.textContent = t; }, 1200);
  });

  document.addEventListener('DOMContentLoaded', updateBar);

  // CSRF: every HTMX request carries the token from the page's meta tag.
  document.body.addEventListener('htmx:configRequest', e => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) e.detail.headers['X-CSRF-Token'] = meta.content;
  });

  // A 303 from an expired session (require_login) or a 403 (bad CSRF) should send
  // the whole page to /login instead of swapping a fragment of it in.
  document.body.addEventListener('htmx:responseError', e => {
    if (e.detail.xhr.status === 403) window.location.href = '/login';
  });
})();

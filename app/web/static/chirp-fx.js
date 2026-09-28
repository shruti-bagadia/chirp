/* Chirp effects: flight, falling leaves, toast, sheet, and forest sounds.
   Everything respects prefers-reduced-motion. Sound is off until you turn it on. */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, r = document) => r.querySelector(s);

  /* ---------- Toast ---------- */
  let toastTimer;
  function toast(msg) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 2800);
  }

  /* ---------- Sheet ---------- */
  function openSheet() { $('#scrim').classList.add('open'); $('#sheet').classList.add('open'); }
  function closeSheet() { $('#scrim').classList.remove('open'); $('#sheet').classList.remove('open'); }

  /* ---------- Falling petals ---------- */
  const PETAL_COLORS = ['#F2B8C4', '#E7A3B1', '#FFFFFF', '#FBD9DF', '#F8EBD3'];
  function leaves(n = 10) {
    if (reduce) return;
    for (let i = 0; i < n; i++) {
      const w = document.createElement('div');
      w.className = 'falling';
      w.style.left = Math.random() * 100 + 'vw';
      w.style.setProperty('--sway', (20 + Math.random() * 40) * (Math.random() < .5 ? -1 : 1) + 'px');
      w.style.setProperty('--dur', (2.6 + Math.random() * 1.6) + 's');
      w.style.setProperty('--flut', (.6 + Math.random() * .6) + 's');
      w.style.animationDelay = Math.random() * .6 + 's';
      const c = PETAL_COLORS[Math.floor(Math.random() * PETAL_COLORS.length)];
      w.innerHTML = `<svg viewBox="0 0 24 24"><path d="M12 2 C17 6 18 13 12 22 C6 13 7 6 12 2 Z" fill="${c}" stroke="rgba(183,84,104,.25)" stroke-width=".8"/></svg>`;
      document.body.appendChild(w);
      setTimeout(() => w.remove(), 5000);
    }
  }

  /* ---------- Sparrow flight ---------- */
  function fly() {
    if (reduce) return;
    const perch = $('#perch');
    const tpl = $('#tpl-sparrow-fly');
    if (!tpl) return;
    const r = perch ? perch.getBoundingClientRect() : { left: 20, top: 80, width: 60 };
    const x0 = r.left + r.width / 2 - 39, y0 = r.top + 4;
    const W = innerWidth;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 140 90');
    svg.classList.add('flyer');
    svg.innerHTML = tpl.content.querySelector('svg').innerHTML;
    if (CSS.supports('offset-path', 'path("M0 0 L1 1")')) {
      const path = `M ${x0} ${y0} C ${x0 + 40} ${y0 - 70}, ${W * .55} ${y0 + 60}, ${W * .8} ${y0 - 10} S ${W + 60} ${y0 - 40}, ${W + 140} ${y0 - 60}`;
      svg.style.offsetPath = `path("${path}")`;
    } else {
      svg.classList.add('no-path');
      svg.style.setProperty('--x0', x0 + 'px');
      svg.style.setProperty('--y0', y0 + 'px');
    }
    if (perch) perch.classList.add('away');
    document.body.appendChild(svg);
    sound.flyAway();
    setTimeout(() => svg.remove(), 1600);
    setTimeout(() => {
      if (!perch) return;
      perch.classList.remove('away');
      perch.classList.add('back');
      setTimeout(() => perch.classList.remove('back'), 800);
    }, 2400);
  }

  /* ---------- Forest sounds (synthesized in the browser, no audio files) ---------- */
  const sound = (() => {
    let ctx, master, natureBus, musicBus, space, started = false;
    const state = { nature: false, music: false, volume: 0.6 };
    const timers = { birds: null, wind: null, music: null, special: null };

    const rnd = (a, b) => a + Math.random() * (b - a);
    const pick = arr => arr[Math.floor(Math.random() * arr.length)];
    const night = () => { const h = new Date().getHours(); return h >= 19 || h < 5; };

    function noise(seconds = 4, brown = true) {
      const len = ctx.sampleRate * seconds, buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
      let last = 0;
      for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        if (brown) { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; } else d[i] = w * 0.5;
      }
      return buf;
    }

    function init() {
      if (started) return;
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
      natureBus = ctx.createGain(); natureBus.gain.value = 0; natureBus.connect(master);
      musicBus = ctx.createGain(); musicBus.gain.value = 0; musicBus.connect(master);
      // A little forest space: filtered feedback echo.
      const delay = ctx.createDelay(1.5), fb = ctx.createGain(), lp = ctx.createBiquadFilter();
      delay.delayTime.value = 0.31; fb.gain.value = 0.32; lp.type = 'lowpass'; lp.frequency.value = 2600;
      space = ctx.createGain(); space.gain.value = 0.35;
      space.connect(delay); delay.connect(lp); lp.connect(fb); fb.connect(delay); lp.connect(master);
      startBrook(); startBreeze();
      started = true;
    }

    /* Beds */
    function startBrook() {
      // Babbling water: white noise through wobbling band-pass filters.
      const src = ctx.createBufferSource(); src.buffer = noise(6, false); src.loop = true;
      const out = ctx.createGain(); out.gain.value = 0.16;
      [700, 1400, 2600].forEach((f, i) => {
        const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = 6;
        const lfo = ctx.createOscillator(), depth = ctx.createGain();
        lfo.frequency.value = 0.9 + i * 0.7; depth.gain.value = f * 0.35;
        lfo.connect(depth).connect(bp.frequency); lfo.start();
        const g = ctx.createGain(); g.gain.value = [0.9, 0.55, 0.25][i];
        src.connect(bp).connect(g).connect(out);
      });
      out.connect(natureBus); src.start();
    }
    function startBreeze() {
      const src = ctx.createBufferSource(); src.buffer = noise(8, true); src.loop = true;
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 420;
      const g = ctx.createGain(); g.gain.value = 0.18;
      src.connect(lp).connect(g).connect(natureBus); src.start();
      const gust = () => {
        if (!state.nature) return;
        const t = ctx.currentTime, peak = rnd(0.35, 0.6), len = rnd(3, 6);
        g.gain.cancelScheduledValues(t);
        g.gain.setTargetAtTime(peak, t, len * 0.25);
        g.gain.setTargetAtTime(0.18, t + len * 0.6, len * 0.3);
        lp.frequency.setTargetAtTime(rnd(600, 900), t, len * 0.3);
        lp.frequency.setTargetAtTime(420, t + len * 0.6, len * 0.3);
        rustleAt(t + len * 0.3, 0.12);
        timers.wind = setTimeout(gust, rnd(9000, 20000));
      };
      timers.wind = setTimeout(gust, 4000);
    }

    /* Building blocks */
    function tone(t, f0, f1, dur, vol, pan = 0, type = 'sine', bus = natureBus, wet = true) {
      const o = ctx.createOscillator(), g = ctx.createGain(), p = ctx.createStereoPanner();
      o.type = type;
      o.frequency.setValueAtTime(f0, t);
      o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(vol, t + Math.min(0.03, dur * 0.3));
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      p.pan.value = pan;
      o.connect(g).connect(p).connect(bus);
      if (wet) p.connect(space);
      o.start(t); o.stop(t + dur + 0.05);
    }
    function rustleAt(t, vol = 0.2) {
      const src = ctx.createBufferSource(); src.buffer = noise(1, false);
      const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = rnd(1800, 3200); bp.Q.value = 0.7;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.08); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
      src.connect(bp).connect(g).connect(natureBus); src.start(t); src.stop(t + 0.8);
    }

    /* Birds of an Indian morning */
    const BIRDS = {
      sparrow(t, pan) { for (let i = 0; i < rnd(3, 6); i++) tone(t + i * rnd(0.16, 0.22), 3500, 2700, 0.08, 0.2, pan); },
      koel(t, pan) {  // rising "ku-oo", each call a little higher
        const n = Math.floor(rnd(3, 6)), base = rnd(780, 880);
        for (let i = 0; i < n; i++) {
          const f = base * (1 + i * 0.07), s = t + i * 0.75;
          tone(s, f, f * 1.18, 0.22, 0.16, pan); tone(s + 0.24, f * 1.18, f * 1.3, 0.3, 0.14, pan);
        }
      },
      dove(t, pan) {  // soft low "croo-croo-cru"
        [[0, 0.32], [0.45, 0.32], [0.9, 0.5]].forEach(([d, len], i) =>
          tone(t + d, 520 - i * 20, 430 - i * 20, len, 0.12, pan, 'triangle'));
      },
      bulbul(t, pan) {  // bubbly warble
        for (let i = 0; i < 5; i++) {
          const f = rnd(1600, 2800);
          tone(t + i * 0.11, f, f * rnd(0.8, 1.25), 0.1, 0.14, pan);
        }
      },
      warbler(t, pan) { for (let i = 0; i < 9; i++) tone(t + i * 0.055, 6400 - i * 240, 5800 - i * 240, 0.045, 0.1, pan); },
      cuckoo(t, pan) { tone(t, 700, 690, 0.28, 0.14, pan); tone(t + 0.36, 560, 550, 0.4, 0.13, pan); },
      woodpecker(t, pan) {  // distant drumming
        const n = Math.floor(rnd(12, 20));
        for (let i = 0; i < n; i++) {
          const s = t + i * 0.055, src = ctx.createBufferSource(); src.buffer = noise(0.05, false);
          const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 1400; bp.Q.value = 3;
          const g = ctx.createGain(), p = ctx.createStereoPanner(); p.pan.value = pan;
          const v = 0.28 * (1 - i / n * 0.5);
          g.gain.setValueAtTime(v, s); g.gain.exponentialRampToValueAtTime(0.0001, s + 0.04);
          src.connect(bp).connect(g).connect(p).connect(natureBus); p.connect(space); src.start(s); src.stop(s + 0.05);
        }
      },
      crickets(t, pan) {
        for (let i = 0; i < 14; i++) tone(t + i * 0.09, 4600, 4550, 0.04, 0.05, pan, 'sine', natureBus, false);
      },
    };
    const DAY = ['sparrow', 'sparrow', 'bulbul', 'bulbul', 'warbler', 'koel', 'dove', 'cuckoo'];
    const NIGHT = ['crickets', 'crickets', 'crickets', 'dove'];

    function birdLoop() {
      if (!state.nature) return;
      const kind = pick(night() ? NIGHT : DAY);
      BIRDS[kind](ctx.currentTime + 0.05, rnd(-0.85, 0.85));
      // Sometimes a second bird answers from the other side.
      if (Math.random() < 0.3 && !night()) BIRDS[pick(['sparrow', 'bulbul', 'warbler'])](ctx.currentTime + rnd(0.8, 1.6), rnd(-0.8, 0.8));
      timers.birds = setTimeout(birdLoop, rnd(2500, 7500));
    }
    function specialLoop() {
      if (!state.nature) return;
      if (!night()) BIRDS.woodpecker(ctx.currentTime + 0.05, rnd(-0.9, 0.9));
      timers.special = setTimeout(specialLoop, rnd(25000, 50000));
    }

    /* Soft melody: a kalimba in a pentatonic scale, wandering gently */
    const SCALE = [293.66, 329.63, 369.99, 440.0, 493.88, 587.33, 659.25, 739.99, 880.0];  // D major pentatonic
    let step = 3;
    function pluck(t, f, vol) {
      tone(t, f, f, 1.6, vol, rnd(-0.3, 0.3), 'sine', musicBus);
      tone(t, f * 2, f * 2, 0.5, vol * 0.25, 0, 'triangle', musicBus);
    }
    function drone() {
      [146.83, 220.0].forEach((f, i) => {
        const o = ctx.createOscillator(), g = ctx.createGain(), lfo = ctx.createOscillator(), d = ctx.createGain();
        o.type = 'sine'; o.frequency.value = f; o.detune.value = i ? 4 : -4;
        g.gain.value = 0.035; lfo.frequency.value = 0.05 + i * 0.03; d.gain.value = 0.02;
        lfo.connect(d).connect(g.gain); o.connect(g).connect(musicBus); o.start(); lfo.start();
      });
    }
    let droneOn = false;
    function phrase() {
      if (!state.music) return;
      if (!droneOn) { drone(); droneOn = true; }
      let t = ctx.currentTime + 0.1;
      const notes = Math.floor(rnd(4, 9));
      for (let i = 0; i < notes; i++) {
        step = Math.max(0, Math.min(SCALE.length - 1, step + pick([-2, -1, -1, 1, 1, 2, 0])));
        pluck(t, SCALE[step], rnd(0.1, 0.16));
        if (Math.random() < 0.2) pluck(t + 0.02, SCALE[Math.max(0, step - 2)], 0.06);
        t += pick([0.45, 0.6, 0.6, 0.9]);
      }
      timers.music = setTimeout(phrase, (t - ctx.currentTime) * 1000 + rnd(2500, 6000));
    }

    /* Controls */
    function fade(bus, on) { bus.gain.setTargetAtTime(on ? 1 : 0, ctx.currentTime, on ? 0.8 : 0.4); }
    function apply() {
      if (!state.nature && !state.music) { if (started) master.gain.setTargetAtTime(0, ctx.currentTime, 0.4); return; }
      init(); ctx.resume();
      master.gain.setTargetAtTime(0.22 * state.volume, ctx.currentTime, 0.5);
      fade(natureBus, state.nature); fade(musicBus, state.music);
    }
    return {
      get state() { return { ...state }; },
      get on() { return state.nature || state.music; },
      setNature(v) { state.nature = v; apply(); clearTimeout(timers.birds); clearTimeout(timers.special); if (v) { birdLoop(); timers.special = setTimeout(specialLoop, 8000); } },
      setMusic(v) { state.music = v; apply(); clearTimeout(timers.music); if (v) phrase(); },
      setVolume(v) { state.volume = v; if (started && this.on) master.gain.setTargetAtTime(0.22 * v, ctx.currentTime, 0.2); },
      toggle() { const on = !this.on; this.setNature(on); this.setMusic(on); return on; },
      flyAway() { if (!this.on) return; const t = ctx.currentTime; tone(t, 2800, 4400, 0.12, 0.25, 0); tone(t + 0.14, 3600, 5200, 0.14, 0.22, 0.3); rustleAt(t, 0.15); },
      rustle() { if (this.on) rustleAt(ctx.currentTime, 0.25); },
      chime() { if (this.on) { const t = ctx.currentTime; pluck(t, 587.33, 0.14); pluck(t + 0.18, 880, 0.12); } },
    };
  })();

  function soundPanel() {
    const st = sound.state;
    const sw = (id, label, sub, on) => `
      <div class="set-row"><span><span style="font-weight:800">${label}</span><br><span class="meta">${sub}</span></span>
      <button class="sw" role="switch" id="${id}" aria-checked="${on}" aria-label="${label}"></button></div>`;
    $('#sheet-body').innerHTML = `
      <h2>Forest sounds</h2>
      <p class="meta" style="margin-top:4px">Made live in your browser. Nothing plays until you switch it on.</p>
      <div class="panel" style="margin:16px 0 0">
        ${sw('snd-nature', 'Birds and brook', 'Sparrows, bulbuls, a koel, doves, a distant woodpecker, water and wind', st.nature)}
        ${sw('snd-music', 'Soft melody', 'A slow kalimba tune over a warm hum', st.music)}
        <div class="set-row"><span style="font-weight:800">Volume</span>
          <input id="snd-vol" type="range" min="0" max="1" step="0.05" value="${st.volume}" aria-label="Volume" style="width:55%;accent-color:#2F3F6B"></div>
      </div>`;
    openSheet();
    const refresh = () => {
      $('#sound').setAttribute('aria-pressed', sound.on);
      $('#sound').setAttribute('aria-label', sound.on ? 'Forest sounds on. Open sound settings' : 'Forest sounds off. Open sound settings');
    };
    $('#snd-nature').addEventListener('click', e => { const v = e.currentTarget.getAttribute('aria-checked') !== 'true'; e.currentTarget.setAttribute('aria-checked', v); sound.setNature(v); refresh(); });
    $('#snd-music').addEventListener('click', e => { const v = e.currentTarget.getAttribute('aria-checked') !== 'true'; e.currentTarget.setAttribute('aria-checked', v); sound.setMusic(v); if (v) sound.chime(); refresh(); });
    $('#snd-vol').addEventListener('input', e => sound.setVolume(parseFloat(e.target.value)));
  }

  function wireSoundButton() {
    const b = $('#sound');
    if (b) b.addEventListener('click', soundPanel);
  }

  function wireSheet() {
    const scrim = $('#scrim');
    if (scrim) scrim.addEventListener('click', closeSheet);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSheet(); });
    document.addEventListener('click', e => { if (e.target.closest('[data-close-sheet]')) closeSheet(); });
  }

  document.addEventListener('DOMContentLoaded', () => { wireSoundButton(); wireSheet(); });

  window.ChirpFX = { toast, openSheet, closeSheet, leaves, fly, sound, reduce };
})();

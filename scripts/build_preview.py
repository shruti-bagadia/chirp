"""Build a single-file, offline preview of the dashboard from the real templates.

    python scripts/build_preview.py  ->  preview/chirp_preview.html

Uses sample data. Actions are simulated in the browser so the preview works without
a server; the real app handles them over HTMX.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.web.demo_store import DemoStore  # noqa: E402
from app.web.templating import greeting, make_env  # noqa: E402

STATIC = ROOT / "app" / "web" / "static"
OUT = ROOT / "preview" / "chirp_preview.html"

SHIM = r"""
(function(){
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  function bar(){const n=$$('#queue-form input[name="ids"]:checked').length,go=$('#go'),lg=$('#letgo');
    if(!go)return;go.disabled=lg.disabled=!n;go.textContent=n?`Ready to fly ${n}`:'Ready to fly';
    const all=$$('#queue-form input[name="ids"]'),pa=$('#pick-all');if(pa)pa.checked=all.length&&n===all.length;
    const c=$('#counts b');if(c)c.textContent=all.length;$('#actionbar').hidden=!all.length;}
  function tab(name){$$('[data-section]').forEach(s=>s.hidden=s.dataset.section!==name);
    $$('nav.tabs a').forEach(a=>a.toggleAttribute('aria-current',a.dataset.tab===name));
    $('#actionbar').hidden=name!=='nest'||!$$('#queue-form input[name="ids"]').length;scrollTo(0,0);}
  document.addEventListener('change',e=>{if(e.target.id==='pick-all')$$('#queue-form input[name="ids"]').forEach(b=>b.checked=e.target.checked);bar();});
  document.addEventListener('click',e=>{
    const a=e.target.closest('nav.tabs a');if(a){e.preventDefault();tab(a.dataset.tab);return;}
    const fo=e.target.closest('.card-open');if(fo){const id=fo.getAttribute('hx-get').split('/').pop();$('#sheet-body').innerHTML=$('#flown-'+id).innerHTML;ChirpFX.openSheet();return;}
    const info=e.target.closest('.info');if(info){const id=info.closest('.row').id.split('-')[1];$('#sheet-body').innerHTML=$('#detail-'+id).innerHTML;ChirpFX.openSheet();return;}
    const bulk=e.target.closest('[data-bulk]');if(bulk){
      const approve=bulk.dataset.bulk==='approve',cls=approve?'lift':'drop';
      const rows=bulk.dataset.id?[$('#row-'+bulk.dataset.id)]:$$('#queue-form input[name="ids"]:checked').map(b=>b.closest('.row'));
      ChirpFX.closeSheet();rows.forEach(r=>r&&r.classList.add(cls));
      if(approve)ChirpFX.fly();else{ChirpFX.leaves(4);ChirpFX.sound.rustle();}
      setTimeout(()=>{rows.forEach(r=>r&&r.remove());bar();ChirpFX.toast(approve?`${rows.length} ready to fly! Chirp takes off at 10:30 AM.`:`Let go of ${rows.length}.`);},560);return;}
    const cb=e.target.closest('.cb');if(cb){const on=cb.getAttribute('aria-pressed')!=='true';$$('[data-cb="'+cb.dataset.cb+'"]').forEach(x=>{x.setAttribute('aria-pressed',on);x.textContent=on?'Callback ✓':'Got a callback?';});if(on){ChirpFX.leaves(12);ChirpFX.toast('A callback! Well flown.');}return;}
    const pill=e.target.closest('.pill');if(pill){ChirpFX.toast(pill.textContent.includes('Find')?'Chirp is looking for new jobs.':'Chirp is taking off.');if(!pill.textContent.includes('Find'))setTimeout(()=>{ChirpFX.fly();},400);return;}
    const hx=e.target.closest('[hx-get],[hx-post]');if(hx&&!e.target.closest('.sound')){const card=hx.closest('.card');
      if(card&&/answer|quick/.test(hx.getAttribute('hx-get')||'')){$('#sheet-body').innerHTML=$('#sheet-'+card.id).innerHTML;ChirpFX.openSheet();return;}
      if(card){card.classList.add('fold');setTimeout(()=>card.remove(),420);ChirpFX.toast('Back in line to fly.');return;}}
    const sub=e.target.closest('#sheet [type=submit], #sheet [hx-post]');if(sub){e.preventDefault();ChirpFX.closeSheet();ChirpFX.leaves(10);ChirpFX.toast('Saved.');}
  });
  document.addEventListener('submit',e=>{e.preventDefault();});
  document.addEventListener('DOMContentLoaded',()=>{bar();tab('nest');});
})();
"""


def main_of(html: str) -> str:
    return html.split("<main>", 1)[1].split("</main>", 1)[0]


def build() -> Path:
    now = datetime.now(UTC)
    s = DemoStore()
    env = make_env()
    base = {
        "greeting": greeting(now),
        "first_name": "Shruti",
        "version": "preview",
        "data_mode": "sample data preview",
        "static": "",
        "preview": True,
        "counts": s.counts(),
        "running": None,
        "paused": False,
        "next_find": s.next_label("find", now),
        "next_fly": s.next_label("apply", now),
        "schedule": s.schedule,
        "tiers": s.settings["ctc_tiers"],
        "limits": s.settings,
    }
    nest = env.get_template("nest.html").render(**base, tab="nest", jobs=s.pending())
    sections = {
        "hands": main_of(env.get_template("hands.html").render(**base, tab="hands", hands=s.hands)),
        "flown": main_of(env.get_template("flown.html").render(**base, tab="flown", flown=s.flown)),
        "more": main_of(env.get_template("more.html").render(**base, tab="more")),
    }
    details = "".join(
        f'<template id="detail-{j.id}">{env.get_template("partials/_detail.html").render(j=j)}</template>'
        for j in s.pending()
    )
    sheets = "".join(
        f'<template id="sheet-hand-{h.id}">'
        f"{env.get_template('partials/_answer.html' if h.kind == 'question' else 'partials/_quick.html').render(h=h)}"
        f"</template>"
        for h in s.hands
        if h.kind in {"question", "quick"}
    )
    flown_sheets = "".join(
        f'<template id="flown-{f.id}">{env.get_template("partials/_flown_detail.html").render(f=f)}</template>'
        for f in s.flown
    )
    main = (
        f'<main><section data-section="nest">{main_of(nest)}</section>'
        + "".join(f'<section data-section="{k}" hidden>{v}</section>' for k, v in sections.items())
        + "</main>"
    )
    html = nest.split("<main>", 1)[0] + main + nest.split("</main>", 1)[1]
    nav_start = html.index('<nav class="tabs"')
    nav_end = html.index("</nav>", nav_start)
    nav = html[nav_start:nav_end]
    for key, path in [("nest", "/"), ("hands", "/hands"), ("flown", "/flown"), ("more", "/more")]:
        nav = nav.replace(f'href="{path}"', f'href="#" data-tab="{key}"', 1)
    html = html[:nav_start] + nav + html[nav_end:]
    css = (STATIC / "chirp.css").read_text(encoding="utf-8")
    fx = (STATIC / "chirp-fx.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/chirp.css">', f"<style>{css}</style>")
    html = html.replace(
        '<script src="/chirp-fx.js" defer></script>',
        f"<script>{fx}</script><script>{SHIM}</script>",
    )
    html = html.replace("</body>", details + sheets + flown_sheets + "</body>")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build())

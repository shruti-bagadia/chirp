"""Render a tailored resume to LaTeX, compile it, and keep it to one page."""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.profile.model import Profile
from app.services.fabrication_check import TailorDraft

TEMPLATES = Path(__file__).parent / "templates"
_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    # En/em dash as TeX's ligature form: the raw Unicode glyph isn't in the
    # charter font's encoding under Tectonic's XeTeX-based pipeline (it just
    # silently drops the character), but "--"/"---" resolve via the font's
    # ligature table under both pdflatex and Tectonic.
    "–": "--",
    "—": "---",
}
_SPECIAL_RE = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIAL))


class CompileError(RuntimeError):
    pass


def latex_escape(value: object) -> str:
    return _SPECIAL_RE.sub(lambda m: _LATEX_SPECIAL[m.group()], str(value))


def emphasize(text: str, phrases: list[str]) -> str:
    """Escape text and bold any of the fact's key numbers ('95%+', '2–6 hours')."""
    phrases = sorted({p for p in phrases if p and p in text}, key=len, reverse=True)
    if not phrases:
        return latex_escape(text)
    pattern = re.compile("|".join(re.escape(p) for p in phrases))
    out, last = [], 0
    for m in pattern.finditer(text):
        out.append(latex_escape(text[last : m.start()]))
        out.append(r"\textbf{" + latex_escape(m.group()) + "}")
        last = m.end()
    out.append(latex_escape(text[last:]))
    return "".join(out)


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        line_comment_prefix="%%",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.filters["e"] = latex_escape
    return env


def _contact_line(identity: dict) -> str:
    links = identity.get("links") or {}
    bits = [latex_escape(identity.get("phone", "")), latex_escape(identity.get("location", ""))]
    if identity.get("email"):
        e = identity["email"]
        bits.append(rf"\href{{mailto:{e}}}{{{latex_escape(e)}}}")
    for key in ("linkedin", "github"):
        if links.get(key):
            url = links[key]
            bits.append(rf"\href{{https://{url}}}{{{latex_escape(url)}}}")
    return r" \;|\; ".join(b for b in bits if b)


def _skill_groups(profile: Profile, priority: list[str]) -> list[tuple[str, list[str]]]:
    rank = {s.lower(): i for i, s in enumerate(priority)}
    groups = []
    for name, items in profile.skill_groups.items():
        ordered = sorted(items, key=lambda s: (rank.get(s.lower(), 999), items.index(s)))
        best = min((rank.get(s.lower(), 999) for s in items), default=999)
        groups.append((best, list(profile.skill_groups).index(name), name, ordered))
    groups.sort()
    return [(name, items) for _, _, name, items in groups]


def build_context(profile: Profile, draft: TailorDraft, company: str) -> dict:
    experiences = []
    for exp in profile.experience:
        bullets = draft.experience.get(exp.id)
        if not bullets:
            continue
        lead, grouped = [], {}
        for b in bullets:
            fact = profile.fact(b.fact_id)
            item = {
                "kind": "bullet",
                "title": fact.title,
                "tools": fact.tools if fact.title else [],
                "text": emphasize(b.text, fact.numbers),
            }
            if fact.group:
                grouped.setdefault(fact.group, []).append(item)
            else:
                lead.append(item)
        items = list(lead)
        for label, group_items in grouped.items():
            items.append({"kind": "group", "label": label})
            items.extend(group_items)
        experiences.append(
            {
                "role": exp.role,
                "dates": exp.dates,
                "company": exp.company,
                "location": exp.location,
                "entries": items,
            }
        )
    summary_numbers = [
        n for f in profile.all_facts() if f.id in draft.summary_fact_ids for n in f.numbers
    ]
    return {
        "name": profile.identity.get("name", ""),
        "title": profile.identity.get("title", ""),
        "contact_line": _contact_line(profile.identity),
        "summary": emphasize(draft.summary, summary_numbers),
        "skill_groups": _skill_groups(profile, draft.skills_priority),
        "experiences": experiences,
        "education": profile.education,
        "recognition": [emphasize(r.text, []) for r in profile.recognition],
        "company": company,
    }


def render_tex(profile: Profile, draft: TailorDraft, company: str) -> str:
    return _env().get_template("resume.tex.j2").render(**build_context(profile, draft, company))


def count_pages(pdf: bytes) -> int:
    """Page count. Uses pypdf (handles compressed PDFs); falls back to a raw scan."""
    if pdf.startswith(b"%PDF-"):
        try:
            import io

            from pypdf import PdfReader

            return len(PdfReader(io.BytesIO(pdf)).pages)
        except Exception:
            pass
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def compile_pdf(tex: str) -> bytes:
    """Compile with Tectonic if installed, else pdflatex."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "resume.tex"
        src.write_text(tex, encoding="utf-8")
        if shutil.which("tectonic"):
            cmd = ["tectonic", "--keep-logs", "--outdir", d, str(src)]
        elif shutil.which("pdflatex"):
            cmd = [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                d,
                str(src),
            ]
        else:
            raise CompileError("Install Tectonic (or a TeX distribution) to build PDFs.")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        pdf = Path(d) / "resume.pdf"
        if proc.returncode != 0 or not pdf.exists():
            tail = (proc.stdout or proc.stderr)[-800:]
            raise CompileError(f"LaTeX failed:\n{tail}")
        return pdf.read_bytes()


@dataclass
class FittedResume:
    pdf: bytes
    tex: str
    draft: TailorDraft
    dropped: list[str]


def fit_one_page(
    profile: Profile,
    draft: TailorDraft,
    company: str,
    *,
    compile_fn: Callable[[str], bytes] = compile_pdf,
    max_attempts: int = 4,
    min_per_experience: int = 2,
) -> FittedResume:
    """Compile; while it's over one page, drop the last bullet of the longest section."""
    d = copy.deepcopy(draft)
    dropped: list[str] = []
    for _ in range(max_attempts + 1):
        tex = render_tex(profile, d, company)
        pdf = compile_fn(tex)
        if count_pages(pdf) <= 1:
            return FittedResume(pdf, tex, d, dropped)
        exp_id = max(d.experience, key=lambda k: len(d.experience[k]))
        if len(d.experience[exp_id]) <= min_per_experience:
            break
        dropped.append(d.experience[exp_id].pop().fact_id)
    raise CompileError("Couldn't fit the resume on one page.")

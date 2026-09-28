"""Your verified facts, loaded from facts.yaml. The only source of resume claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ProfileError(ValueError):
    pass


@dataclass(slots=True)
class Fact:
    id: str
    text: str
    numbers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    title: str | None = None  # project name, rendered as-is (never rewritten)
    group: str | None = None  # sub-heading such as "Client – Poonawalla Fincorp Ltd"


@dataclass(slots=True)
class Experience:
    id: str
    company: str
    role: str
    dates: str
    location: str = ""
    facts: list[Fact] = field(default_factory=list)


@dataclass(slots=True)
class Profile:
    identity: dict
    positioning: str
    experience: list[Experience]
    education: list[dict]
    recognition: list[Fact]
    skills_allowed: list[str]
    skill_groups: dict[str, list[str]]
    never_claim: list[str]
    version: int = 0

    @classmethod
    def from_dict(cls, d: dict, version: int = 0) -> Profile:
        def fact(x: dict) -> Fact:
            if "id" not in x or "text" not in x:
                raise ProfileError(f"Every fact needs an id and text: {x}")
            return Fact(
                id=x["id"],
                text=x["text"].strip(),
                numbers=[str(n) for n in x.get("numbers") or []],
                tools=list(x.get("tools") or []),
                tags=list(x.get("tags") or []),
                title=x.get("title"),
                group=x.get("group"),
            )

        experience = [
            Experience(
                id=e["id"],
                company=e["company"],
                role=e["role"],
                dates=e["dates"],
                location=e.get("location", ""),
                facts=[fact(f) for f in e.get("facts") or []],
            )
            for e in d.get("experience") or []
        ]
        skills = d.get("skills") or {}
        groups = skills.get("groups") or {}
        allowed = list(
            dict.fromkeys(
                [*(skills.get("allowed") or []), *(s for g in groups.values() for s in g)]
            )
        )
        p = cls(
            identity=d.get("identity") or {},
            positioning=d.get("positioning", ""),
            experience=experience,
            education=list(d.get("education") or []),
            recognition=[fact(r) for r in d.get("recognition") or []],
            skills_allowed=allowed,
            skill_groups={k: list(v) for k, v in groups.items()},
            never_claim=[s.lower() for s in d.get("never_claim") or []],
            version=version,
        )
        ids = [f.id for f in p.all_facts()]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ProfileError(f"Duplicate fact ids: {sorted(dupes)}")
        return p

    @classmethod
    def load(cls, path: str | Path, version: int = 0) -> Profile:
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")), version)

    def all_facts(self) -> list[Fact]:
        return [f for e in self.experience for f in e.facts] + list(self.recognition)

    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.all_facts() if f.id == fact_id), None)

    def experience_by_id(self, exp_id: str) -> Experience | None:
        return next((e for e in self.experience if e.id == exp_id), None)

    def companies(self) -> set[str]:
        return {e.company for e in self.experience}

    def prompt_block(self) -> str:
        """Facts as the LLM sees them: IDs, text, allowed numbers and tools. No contact details."""
        lines = [
            f"Title: {self.identity.get('title', '')}",
            f"Years of experience: {self.identity.get('years', '')}",
            f"Positioning: {self.positioning}",
            "",
        ]
        for e in self.experience:
            lines.append(f"## {e.id}: {e.role}, {e.company} ({e.dates})")
            for f in e.facts:
                head = f"{f.title}: " if f.title else ""
                meta = []
                if f.numbers:
                    meta.append("numbers " + ", ".join(f.numbers))
                if f.tools:
                    meta.append("tools " + ", ".join(f.tools))
                lines.append(
                    f"- [{f.id}] {head}{f.text}" + (f"  ({'; '.join(meta)})" if meta else "")
                )
            lines.append("")
        if self.recognition:
            lines.append("## recognition")
            lines += [f"- [{r.id}] {r.text}" for r in self.recognition]
            lines.append("")
        lines.append("Allowed skills: " + ", ".join(self.skills_allowed))
        return "\n".join(lines)

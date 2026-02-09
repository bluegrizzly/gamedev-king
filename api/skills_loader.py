"""
Agent Skills integration: discover skills in api/skills, parse SKILL.md frontmatter,
and provide metadata for the system prompt plus full content for activation.

Follows progressive disclosure: metadata in prompt, full SKILL.md loaded via load_skill when used.
Ref: https://agentskills.io/integrate-skills
Ref: https://developers.openai.com/codex/skills/
"""

from pathlib import Path
import re

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
SKILL_FILENAME = "SKILL.md"
OPENAI_YAML = "agents/openai.yaml"


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML-like frontmatter between first --- and second ---."""
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    block = match.group(1)
    result: dict[str, str] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or not ":" in line:
            continue
        idx = line.index(":")
        key = line[:idx].strip()
        value = line[idx + 1 :].strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1].replace('\\"', '"').replace("\\'", "'")
        result[key] = value
    return result


def _parse_openai_yaml(skill_dir: Path) -> dict[str, str]:
    """
    Optional agents/openai.yaml (OpenAI/Codex convention): read display_name and short_description.
    See https://developers.openai.com/codex/skills/ — interface.display_name, interface.short_description.
    """
    path = skill_dir / OPENAI_YAML
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    out: dict[str, str] = {}
    for line in raw.split("\n"):
        s = line.strip()
        if s.startswith("display_name:"):
            val = s[len("display_name:"):].strip().strip('"\'')
            if val:
                out["display_name"] = val
        elif s.startswith("short_description:"):
            val = s[len("short_description:"):].strip().strip('"\'')
            if val:
                out["short_description"] = val
    return out


def discover_skills() -> list[dict]:
    """
    Discover skills: each subfolder of SKILLS_DIR that contains SKILL.md.
    Uses agents/openai.yaml display_name and short_description when present (OpenAI/Codex convention).
    Returns list of {"name": str, "description": str, "path": str} (path = folder name).
    """
    if not SKILLS_DIR.is_dir():
        return []
    out: list[dict] = []
    for entry in SKILLS_DIR.iterdir():
        if not entry.is_dir():
            continue
        skill_md = entry / SKILL_FILENAME
        if not skill_md.is_file():
            continue
        try:
            raw = skill_md.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _parse_frontmatter(raw)
        oy = _parse_openai_yaml(entry)
        # name = canonical id for load_skill (frontmatter or folder); description = for matching/display
        name = (fm.get("name") or entry.name).strip() or entry.name
        description = (oy.get("short_description") or fm.get("description") or "").strip()
        out.append({
            "name": name,
            "description": description,
            "path": entry.name,
        })
    return out


def get_skill_content(skill_name: str) -> str | None:
    """
    Load full SKILL.md content for a skill by name (folder name or frontmatter name).
    Returns None if not found.
    """
    if not SKILLS_DIR.is_dir():
        return None
    skill_name = skill_name.strip().lower()
    for entry in SKILLS_DIR.iterdir():
        if not entry.is_dir():
            continue
        skill_md = entry / SKILL_FILENAME
        if not skill_md.is_file():
            continue
        if entry.name.lower() == skill_name:
            try:
                return skill_md.read_text(encoding="utf-8")
            except Exception:
                return None
        try:
            raw = skill_md.read_text(encoding="utf-8")
            fm = _parse_frontmatter(raw)
            if (fm.get("name") or "").strip().lower() == skill_name:
                return raw
        except Exception:
            continue
    return None


def build_available_skills_xml() -> str:
    """
    Build <available_skills> XML block for the system prompt (progressive disclosure).
    Descriptions define when to trigger; keep them concise (~50–100 tokens per skill).
    """
    skills = discover_skills()
    if not skills:
        return ""
    parts = []
    for s in skills:
        name = _escape_xml(s["name"])
        desc = _escape_xml((s["description"] or "")[:400])
        parts.append(f'  <skill>\n    <name>{name}</name>\n    <description>{desc}</description>\n  </skill>')
    return "<available_skills>\n" + "\n".join(parts) + "\n</available_skills>"


def _escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

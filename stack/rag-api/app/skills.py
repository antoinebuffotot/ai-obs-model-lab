"""Agent Skills (SKILL.md) as knowledge for the Dynatrace sub-agent, e.g. from github.com/Dynatrace/dynatrace-for-ai.

The participants choose which skills the agent gets by copying skill folders into stack/skills (/workspace/skills):

    skills/<name>/SKILL.md            front matter (name, description) + instructions
    skills/<name>/references/*.md     details, read on demand

The agent sees only the short list (name + description) in its instruction, and reads a skill with read_skill when
it needs it (progressive disclosure: the context stays small). Reading is bounded: a long skill is truncated.
"""
import logging
import os
import re

log = logging.getLogger("skills")

SKILLS_DIR = os.getenv("SKILLS_DIR", "/workspace/skills")
MAX_CHARS = int(os.getenv("SKILL_MAX_CHARS", "6000"))
MAX_DEPTH = 4
SKIP_DIRS = {".git", "node_modules", "__pycache__", "tests", ".github"}
TEXT_EXT = {".md", ".txt", ".yaml", ".yml", ".json", ".dql"}

LIST_SCHEMA = {"type": "function", "function": {
    "name": "list_skills",
    "description": "List the available skills (Dynatrace know-how: DQL syntax, logs, problems...) with their description.",
    "parameters": {"type": "object", "properties": {}}}}
READ_SCHEMA = {"type": "function", "function": {
    "name": "read_skill",
    "description": "Read the instructions of a skill (e.g. before writing a DQL query). Optionally read one of its "
                   "reference files, listed at the end of the skill.",
    "parameters": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string", "description": "Skill name, as given by list_skills"},
        "reference": {"type": "string", "description": "Optional relative path of a reference file, e.g. references/x.md"}}}}}


def _front_matter(text: str) -> tuple[dict, str]:
    """Minimal YAML front matter parser (key: value, folded or literal blocks); returns (fields, body)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return {}, text
    fields, key = {}, None
    for line in m.group(1).split("\n"):
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv and not line.startswith(" "):
            key, value = kv.group(1), kv.group(2).strip()
            fields[key] = "" if value in (">", "|", ">-", "|-") else value.strip("'\"")
        elif key and line.strip():
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields, text[m.end():]


def scan() -> dict[str, dict]:
    """Skills found under SKILLS_DIR (a SKILL.md in any sub folder, up to MAX_DEPTH levels)."""
    found: dict[str, dict] = {}
    if not os.path.isdir(SKILLS_DIR):
        return found
    base_depth = SKILLS_DIR.rstrip("/\\").count(os.sep)
    for root, dirs, files in os.walk(SKILLS_DIR):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        if "SKILL.md" not in files:
            continue
        try:
            with open(os.path.join(root, "SKILL.md"), encoding="utf-8") as f:
                fields, _ = _front_matter(f.read())
        except OSError:
            continue
        name = fields.get("name") or os.path.basename(root)
        found.setdefault(name, {"name": name, "description": fields.get("description", ""), "dir": root})
    return found


def count() -> int:
    return len(scan())


def status() -> dict:
    return {"dir": SKILLS_DIR, "count": count(), "names": sorted(scan())}


def schemas() -> list[dict]:
    return [LIST_SCHEMA, READ_SCHEMA] if count() else []


def prompt_section(max_chars: int = 1800) -> str:
    """Short list of the skills for the agent instruction."""
    skills = scan()
    if not skills:
        return ""
    lines, size = [], 0
    for s in skills.values():
        desc = re.sub(r"\s+", " ", s["description"]).strip()
        line = f"- {s['name']}: {desc[:140]}"
        if size + len(line) > max_chars:
            lines.append("- (more skills: use list_skills)")
            break
        lines.append(line)
        size += len(line)
    return ("\n\nSkills available (read one with read_skill before writing DQL or when you need Dynatrace know-how):\n"
            + "\n".join(lines))


def list_skills() -> str:
    skills = scan()
    if not skills:
        return "Aucune skill installée (dossier vide)."
    return "\n".join(f"- {s['name']}: {re.sub(chr(10), ' ', s['description'])[:300]}" for s in skills.values())


def _find(name: str):
    skills = scan()
    if name in skills:
        return skills[name]
    low = name.strip().lower()
    for key, s in skills.items():
        if key.lower() == low or key.lower().startswith(low):
            return s
    return None


def read_skill(name: str, reference: str = "") -> str:
    skill = _find(str(name))
    if not skill:
        return f"Skill « {name} » introuvable. Disponibles : {', '.join(sorted(scan())) or 'aucune'}."
    base = os.path.realpath(skill["dir"])
    if reference:
        path = os.path.realpath(os.path.join(base, str(reference)))
        if os.path.commonpath([base, path]) != base or not os.path.isfile(path) \
                or os.path.splitext(path)[1].lower() not in TEXT_EXT:
            return f"Référence « {reference} » introuvable dans la skill {skill['name']}."
    else:
        path = os.path.join(base, "SKILL.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as exc:
        return f"Lecture impossible : {exc}"
    if not reference:
        text = _front_matter(text)[1]
    out = text[:MAX_CHARS]
    if len(text) > MAX_CHARS:
        out += f"\n[... tronqué : {len(text) - MAX_CHARS} caractères restants]"
    if not reference:
        refs = []
        ref_dir = os.path.join(base, "references")
        if os.path.isdir(ref_dir):
            for r, _, fs in os.walk(ref_dir):
                for f in sorted(fs):
                    refs.append(os.path.relpath(os.path.join(r, f), base).replace(os.sep, "/"))
        if refs:
            out += "\n\nReference files (read_skill with `reference`): " + ", ".join(refs[:20])
    return out

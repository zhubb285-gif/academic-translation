"""Journal corpus retrieval. English phrase occurrences are usage evidence, not bilingual proof."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from statistics import median

DATA = Path(__file__).resolve().parents[1] / "data/journal_library"
SKILLS = Path(__file__).resolve().parents[3] / "skills/journals"
CATALOG = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def _load_articles(stamp: int) -> list[dict]:
    path = DATA / "articles.json"
    return json.loads(path.read_text(encoding="utf-8")).get("articles", []) if path.exists() else []


def articles() -> list[dict]:
    path = DATA / "articles.json"
    return _load_articles(path.stat().st_mtime_ns if path.exists() else 0)


def journal_config(name: str) -> dict | None:
    return next((j for j in CATALOG["journals"] if j["name"].casefold() == name.casefold()), None)


def public_article(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "paragraphs"}


def journal_summary(name: str) -> dict:
    config = journal_config(name)
    own = [a for a in articles() if a["journal"] == name]
    return {"name": name, "slug": config["slug"] if config else None,
            "article_count": len(own), "full_text_count": sum(a["text_kind"] == "full_text" for a in own),
            "abstract_count": sum(a["text_kind"] == "abstract" for a in own),
            "domains": {d: sum(d in a.get("domains", []) for a in own) for d in CATALOG["domains"]},
            "skill_available": bool(config and (SKILLS / config["slug"] / "SKILL.md").is_file()),
            "coverage_note": CATALOG["coverage_note"]}


def search_usage(term: str, candidates: list[str], domain: str = "", preferred_journal: str = "", limit: int = 12) -> list[dict]:
    queries = list(dict.fromkeys(c.strip() for c in [term, *candidates] if c and not re.search(r"[\u4e00-\u9fff]", c)))
    if not queries:
        return []
    # Natural-science homonyms must not be offered for unrepresented humanities disciplines.
    if any(w in domain for w in ("马克思", "法学", "法理", "法律", "政治理论")):
        return []
    hits = []
    for article in articles():
        if article.get("retracted") or not article.get("verification"):
            continue
        for candidate in queries:
            pattern = re.compile(r"(?<!\w)" + re.escape(candidate).replace(r"\ ", r"[\s\-–]+") + r"(?!\w)", re.I)
            for paragraph in article.get("paragraphs", []):
                match = pattern.search(paragraph)
                if not match:
                    continue
                start, end = max(0, match.start() - 130), min(len(paragraph), match.end() + 230)
                quote = ("…" if start else "") + paragraph[start:end] + ("…" if end < len(paragraph) else "")
                hits.append({
                    "article_id": article["id"], "title": article["title"], "doi": article["doi"],
                    "journal": article["journal"], "text_kind": article["text_kind"],
                    "text_source_url": article["text_source_url"], "source_url": article["article_url"],
                    "source_name": article["journal"], "source_level": 2, "source_type": "journal_usage",
                    "evidence_group": "journal", "evidence_text": quote,
                    "candidate_translation": candidate, "recommended_translation": candidate,
                    "published_date": article.get("published_date"), "domains": article.get("domains", []),
                    "source_checked": True, "is_valid": True, "match_type": "english_usage",
                    "status_tag": "英文用法·待人工对应", "domain": domain,
                    "recommendation_reason": "已在实际文章文本中找到完整英文表达；仅证明英文用法，不自动证明中文与英文含义对应。请结合专业语境人工裁决。",
                    "text_sha256": article["text_sha256"],
                })
                break
    hits.sort(key=lambda h: (h["journal"] != preferred_journal, h["text_kind"] != "full_text", -(int((h.get("published_date") or "0")[:4]))))
    # Keep different candidate expressions and journals represented.
    selected, seen = [], set()
    for hit in hits:
        key = (hit["journal"], hit["candidate_translation"].casefold())
        if key not in seen:
            selected.append(hit)
            seen.add(key)
    for hit in hits:
        if len(selected) >= limit:
            break
        if hit not in selected:
            selected.append(hit)
    return selected[:limit]


def style_skill(name: str) -> dict | None:
    config = journal_config(name)
    if not config:
        return None
    folder = SKILLS / config["slug"]
    path = folder / "SKILL.md"
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    profile = json.loads((folder / "references/profile.json").read_text())
    return {**journal_summary(name), "skill_name": f"translate-{config['slug']}", "content": content,
            "version": hashlib.sha256(content.encode()).hexdigest()[:12], "profile": profile,
            "references": [public_article(a) for a in articles() if a["journal"] == name]}


def style_instruction(name: str, section: str = "") -> str:
    skill = style_skill(name)
    if not skill:
        return ""
    # Inject maintained instructions, never entire raw articles into the instruction channel.
    body = skill["content"].split("---", 2)[-1].strip()
    return f"【已选择的期刊风格 Skill：{skill['skill_name']} / {skill['version']}】\n{body}\n当前处理章节：{section or '正文'}。仅将样本统计用于风格参考，不得据此改动事实或套用其他章节结构。"

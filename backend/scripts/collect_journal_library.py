"""Collect traceable journal abstracts and optionally reuse licensed local full text.

Run from backend: .venv/bin/python scripts/collect_journal_library.py --target 40
OpenAlex abstracts are indexed source text, NOT verified bilingual pairs or full papers.
No credentials, paid endpoints, or synthetic articles are used.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from datetime import date, datetime, timezone
import xml.etree.ElementTree as ET

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app/data/journal_library"
CATALOG = json.loads((DATA / "catalog.json").read_text())
sys.path.insert(0, str(ROOT))


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def classify(text):
    low = text.lower()
    return [name for name, words in CATALOG["domains"].items() if any(w in low for w in words)]


def reconstruct(index):
    tokens = {position: word for word, positions in (index or {}).items() for position in positions}
    return clean(" ".join(tokens[p] for p in sorted(tokens)))


def load_previous(folder, collected):
    manifest = json.loads((folder / "data/manifest.json").read_text())
    config_by_name = {j["name"].casefold(): j for j in CATALOG["journals"]}
    for item in manifest["articles"]:
        journal = config_by_name.get(item.get("journal", "").casefold())
        if not journal or not item.get("training_eligible") or item.get("license") not in ("CC-BY", "CC0"):
            continue
        path = folder / (item.get("fulltext_path") or "missing")
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.get("fulltext_sha256"):
            continue
        tree = ET.fromstring(raw)
        sections = []
        for node in tree.findall(".//abstract") + tree.findall(".//body"):
            # Individual paragraphs keep source sentence order, excluding references and SI.
            sections.extend(clean(" ".join(p.itertext())) for p in node.findall(".//p"))
        abstract_node = tree.find(".//abstract")
        abstract = clean(" ".join(abstract_node.itertext())) if abstract_node is not None else ""
        if not sections or not item.get("doi"):
            continue
        doi = item["doi"].lower()
        collected[doi] = {
            "id": hashlib.sha256(doi.encode()).hexdigest()[:20], "doi": doi,
            "journal_slug": journal["slug"], "journal": journal["name"], "issn": journal["issn"],
            "title": clean(item["title"]), "authors": item.get("authors"),
            "year": int(item["year"]), "published_date": item.get("first_publication_date"),
            "abstract": abstract, "text_kind": "full_text", "paragraphs": sections,
            "domains": classify(item["title"] + " " + abstract),
            "article_url": "https://doi.org/" + doi, "text_source_url": item["source_url"],
            "metadata_url": item.get("discovery_url"), "license": item["license"],
            "license_url": item.get("license_url"), "retrieved_at": item.get("download_date"),
            "text_sha256": hashlib.sha256("\n".join(sections).encode()).hexdigest(),
            "verification": "repository_xml_and_original_sha256", "retracted": False,
        }


def collect(args):
    DATA.mkdir(parents=True, exist_ok=True)
    destination = DATA / "articles.json"
    collected = {a["doi"]: a for a in json.loads(destination.read_text()).get("articles", [])} if destination.exists() else {}
    if args.previous_corpus:
        load_previous(Path(args.previous_corpus), collected)
    cache = ROOT / "data/literature_cache"
    cache.mkdir(parents=True, exist_ok=True)
    errors = []
    today = date.today().isoformat()
    with httpx.Client(timeout=55, headers={"User-Agent": "AcademicTranslation-JournalLibrary/1.0"}) as client:
        for journal in CATALOG["journals"]:
            # Query each applicable subject so a single high-citation topic cannot fill the library.
            for query in journal["queries"]:
                params = {"filter": f"primary_location.source.issn:{journal['issn']},to_publication_date:{today},has_abstract:true,is_retracted:false",
                          "search": query, "per-page": min(100, max(25, args.target)), "sort": "cited_by_count:desc"}
                cache_path = cache / f"{journal['slug']}-{hashlib.sha256(query.encode()).hexdigest()[:8]}.json"
                payload = None
                if cache_path.exists() and not args.refresh:
                    payload = json.loads(cache_path.read_text())
                else:
                    for attempt in range(3):
                        try:
                            response = client.get("https://api.openalex.org/works", params=params)
                            response.raise_for_status()
                            payload = response.json()
                            cache_path.write_text(json.dumps(payload, ensure_ascii=False))
                            break
                        except (httpx.HTTPError, ValueError) as exc:
                            if attempt == 2:
                                errors.append({"journal": journal["name"], "query": query, "error": str(exc)[:180]})
                            else:
                                time.sleep(2 ** (attempt + 1))
                    time.sleep(1)
                for item in (payload or {}).get("results", []):
                    doi = (item.get("doi") or "").removeprefix("https://doi.org/").lower()
                    text = reconstruct(item.get("abstract_inverted_index"))
                    source = (item.get("primary_location") or {}).get("source") or {}
                    title = clean(item.get("title"))
                    if (not doi or journal["issn"] not in (source.get("issn") or [])
                            or item.get("is_retracted") or len(text.split()) < 60
                            or item.get("language") not in ("en", None)
                            or re.search(r"\b(correction|retraction|erratum|corrigendum)\b", title, re.I)):
                        continue
                    if doi in collected:
                        continue
                    collected[doi] = {
                        "id": hashlib.sha256(doi.encode()).hexdigest()[:20], "doi": doi,
                        "journal_slug": journal["slug"], "journal": journal["name"], "issn": journal["issn"],
                        "title": title, "authors": [a.get("author", {}).get("display_name") for a in item.get("authorships", [])[:15]],
                        "year": item.get("publication_year"), "published_date": item.get("publication_date"),
                        "abstract": text, "paragraphs": [text], "text_kind": "abstract",
                        "domains": classify(title + " " + text), "article_url": "https://doi.org/" + doi,
                        "text_source_url": item["id"], "metadata_url": str(httpx.URL("https://api.openalex.org/works", params=params)),
                        "license": "indexed_abstract; article_rights_not_inferred",
                        "license_url": None, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "verification": "openalex_primary_journal_issn_and_doi", "retracted": False,
                        "discovery_query": query,
                    }
                own = [a for a in collected.values() if a["journal_slug"] == journal["slug"]]
                print(f"{journal['name']} / {query}: {len(own)} texts", flush=True)
            destination.write_text(json.dumps({"schema_version": 1, "generated_at": today, "articles": list(collected.values())}, ensure_ascii=False, indent=2))
    counts = {j["name"]: sum(a["journal_slug"] == j["slug"] for a in collected.values()) for j in CATALOG["journals"]}
    report = {"generated_at": today, "counts": counts, "total": len(collected), "full_text": sum(a["text_kind"] == "full_text" for a in collected.values()),
              "abstract_only": sum(a["text_kind"] == "abstract" for a in collected.values()), "errors": errors,
              "limitations": [CATALOG["coverage_note"], "英文用法出现不等于中英译法得到证实，必须人工裁决。", "摘要样本只能支撑摘要风格观察，不能推出正文或方法章节风格。", "摘要获取不代表获得全文下载或模型训练授权。"]}
    (DATA / "collection_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(n >= 10 for n in counts.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=40, help="results per subject query; all usable results retained")
    parser.add_argument("--previous-corpus", help="existing licensed corpus root containing data/manifest.json")
    parser.add_argument("--refresh", action="store_true")
    raise SystemExit(collect(parser.parse_args()))

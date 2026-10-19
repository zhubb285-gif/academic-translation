"""Shared source policy, migrated from the existing project configuration."""
import json
from pathlib import Path
from urllib.parse import urlsplit

# Keep public source configuration separate from ignored private runtime data.
DATA = Path(__file__).resolve().parents[1] / "data"
POLICY = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
SEARCH_TEMPLATES = json.loads((DATA / "source_search_templates.json").read_text(encoding="utf-8"))
HOMEPAGES = {
    "T1-01": "https://english.www.gov.cn/", "T1-02": "https://en.moe.gov.cn/",
    "T1-03": "https://english.scio.gov.cn/", "T1-04": "https://www.swpu.edu.cn/",
    "T1-05": "https://openstd.samr.gov.cn/bzgk/gb/", "T1-06": "https://www.termonline.cn/",
    "T1-07": "https://www.cas.cn/", "T1-09": "https://www.imsilkroad.com/",
    "T2-01": "https://kns.cnki.net/",
    "T2-04": "https://link.springer.com/", "T2-08": "https://www.datapages.com/",
    "T2-18": "https://term.catl.org.cn/",
}

SOURCES = []
for tier, group in POLICY["tiers"].items():
    for row in group["sources"]:
        SOURCES.append({**row, "source_level": int(tier[-1]), "blocked": tier == "tier3",
                        "rule": group["rule"], "origin": "既有信源清单",
                        "url": HOMEPAGES.get(row["id"], "https://" + row["domains"][0] + "/" if row["domains"] else "")})

# Additional disciplinary sources use a separate, explicit extension to the old list.
for ident, name, domain, level in [
    ("mesh", "NCBI MeSH", "ncbi.nlm.nih.gov", 1),
    ("iupac", "IUPAC Gold Book", "goldbook.iupac.org", 1),
    ("iso", "ISO 国际标准", "iso.org", 2),
    ("ieee", "IEEE Xplore", "ieeexplore.ieee.org", 2),
    ("acm", "ACM Digital Library", "dl.acm.org", 2),
    ("nature", "Nature", "nature.com", 2),
    ("science", "Science", "science.org", 2),
    ("cell", "Cell Press", "cell.com", 2),
    ("pnas", "PNAS", "pnas.org", 2),
]:
    SOURCES.append({"id": "EXT-" + ident, "name": name, "domains": [domain],
                    "source_level": level, "blocked": False, "origin": "学科补充信源",
                    "rule": POLICY["tiers"][f"tier{level}"]["rule"],
                    "url": "https://" + domain + "/"})

next(s for s in SOURCES if s["id"] == "EXT-mesh")["url"] = "https://www.ncbi.nlm.nih.gov/mesh/"


def find_source(url: str = "", name: str = "") -> dict | None:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    matches = [(len(domain), source) for source in SOURCES for domain in source["domains"]
               if host == domain or host.endswith("." + domain)]
    if matches:
        return max(matches, key=lambda pair: pair[0])[1]
    # Only exact names are safe when repairing records with missing URLs.
    if not url and name:
        return next((s for s in SOURCES if name in (s["name"], s.get("original_name"))), None)
    return None


def source_catalog(term: str, candidate: str = "") -> list[dict]:
    from app.services.source_links import search_link
    result = []
    for source in SOURCES:
        variants = []
        for domain in source["domains"]:
            url = source["url"] if domain == source["domains"][0] else "https://" + domain + "/"
            variants.append({"url": url, "domain": domain, **search_link(url, term, candidate)})
        result.append({**source, "links": variants})
    return result

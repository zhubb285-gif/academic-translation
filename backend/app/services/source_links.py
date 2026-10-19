"""Resolve source links without confusing a search page with an evidence page."""
import base64
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from app.services.source_catalog import SEARCH_TEMPLATES, find_source


def search_link(url: str, term: str, candidate: str = "") -> dict:
    """Only offer searches run by the source itself, with the current term filled in."""
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or parsed.username:
            raise ValueError("Unsupported link")
    except ValueError:
        return {"search_url": "", "search_label": "", "search_term": ""}
    if not host:
        return {"search_url": "", "search_label": "缺少来源网址", "search_term": ""}
    source = find_source(url)
    if source and source["blocked"]:
        return {"search_url": "", "search_label": "三级弱源，不用于查证", "search_term": term,
                "search_kind": "blocked", "source_blocked": True}
    query = (candidate or term).strip()
    if not query:
        return {"search_url": "", "search_label": "请先输入术语", "search_term": ""}
    templates = [(len(domain), spec) for domain, spec in SEARCH_TEMPLATES.items()
                 if (host == domain or host.endswith("." + domain))
                 and (domain != "gov.cn" or host in ("gov.cn", "www.gov.cn", "sousuo.www.gov.cn"))]
    # Prefer a host-specific rule, e.g. the English government search rather than gov.cn.
    if templates:
        spec = max(templates, key=lambda pair: pair[0])[1]
        query = term.strip() if spec.get("query_lang") == "zh" else query
        if spec.get("kind") == "site-search":
            encoded = quote(query, safe="")
            if spec.get("encode") == "double":
                encoded = quote(encoded, safe="")
            elif spec.get("encode") == "base64-uri":
                encoded = quote(base64.b64encode(encoded.encode("ascii")).decode("ascii"), safe="")
            return {"search_url": spec["url"].replace("{q}", encoded),
                    "search_label": spec["label"] + " ↗", "search_term": query,
                    "search_kind": "internal", "source_blocked": False}
    if host in ("termonline.cn", "www.termonline.cn"):
        name = "术语在线"
        query = term
        target = "https://www.termonline.cn/search?" + urlencode({"searchText": query})
    elif host in ("nature.com", "www.nature.com"):
        name = "Nature"
        target = "https://www.nature.com/search?" + urlencode({"q": query})
    elif host in ("iso.org", "www.iso.org"):
        name = "ISO"
        target = "https://www.iso.org/search.html?" + urlencode({"q": query})
    elif host == "ieeexplore.ieee.org":
        name = "IEEE Xplore"
        target = "https://ieeexplore.ieee.org/search/searchresult.jsp?" + urlencode({"newsearch": "true", "queryText": query})
    elif host == "dl.acm.org":
        name = "ACM"
        target = "https://dl.acm.org/action/doSearch?" + urlencode({"AllField": query})
    elif host in ("ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"):
        name = "MeSH"
        target = "https://www.ncbi.nlm.nih.gov/mesh/?" + urlencode({"term": query})
    elif host in ("eric.ed.gov", "www.eric.ed.gov"):
        name = "ERIC"
        target = "https://eric.ed.gov/?" + urlencode({"q": query})
    elif host in ("bakerhughes.com", "www.bakerhughes.com"):
        name = "Baker Hughes"
        target = "https://www.bakerhughes.com/search?" + urlencode({"search": query})
    else:
        return {"search_url": "", "search_label": "暂未接通带词站内检索", "search_term": query,
                "search_kind": "unavailable", "source_blocked": False}
    return {"search_url": target, "search_label": f"在{name}查看检索结果 ↗", "search_term": query,
            "search_kind": "internal", "source_blocked": False}


def source_link(url: str, term: str, candidate: str = "") -> dict:
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not host or parsed.username:
            return {"source_url": "", "link_kind": "unavailable", "link_label": "暂无可核对链接"}
    except ValueError:
        return {"source_url": "", "link_kind": "unavailable", "link_label": "暂无可核对链接"}
    query = parse_qs(parsed.query)
    path = parsed.path.rstrip("/")
    if host in ("termonline.cn", "www.termonline.cn"):
        if path in ("/wordDetail", "/wordDetailByStandard") and query.get("subject") and query.get("termName"):
            return {"source_url": url, "link_kind": "entry", "link_label": "打开官方词条 ↗"}
        # The public site uses searchText, not the obsolete `k` parameter.
        url = "https://www.termonline.cn/search?" + urlencode({"searchText": term})
    elif host in ("nature.com", "www.nature.com") and (not path or path == "/search"):
        url = "https://www.nature.com/search?" + urlencode({"q": candidate or term})
    elif not path or path in ("/en", "/english", "/standards", "/SJ", "/obp", "/search", "/search-results", "/search.html") or host in ("www.google.com", "google.com"):
        link = search_link(url, term, candidate)
        if not link["search_url"]:
            return {"source_url": "", "link_kind": "unavailable", "link_label": link["search_label"]}
        url = link["search_url"]
    else:
        return {"source_url": url, "link_kind": "entry", "link_label": "打开来源详情页 ↗"}
    return {"source_url": url, "link_kind": "search", "link_label": "带入此词检索（待核对）↗"}


def present_card(card: dict, term: str, trusted: bool = False) -> dict:
    """Old generated quotations must not be presented as retrieved original text."""
    result = dict(card)
    source = find_source(card.get("source_url", ""), card.get("source_name", ""))
    url = card.get("source_url") or (source["url"] if source else "")
    result["original_url"] = url if source_link(url, term)["source_url"] else ""
    result.update(search_link(url, term, card.get("recommended_translation", "")))
    result.update(source_link(url, term, card.get("recommended_translation", "")))
    result["source_blocked"] = bool(source and source["blocked"])
    if source:
        result["source_level"] = source["source_level"]
        if card.get("source_name") == source.get("original_name"):
            result["source_name"] = source["name"]
    checked = trusted and not result["source_blocked"] and result["link_kind"] == "entry" and bool(card.get("evidence_text"))
    result["source_checked"] = checked
    if not checked and result["link_kind"] == "entry":
        result["link_label"] = "打开页面（待核对）↗"
    if not checked:
        result.update({
            "evidence_text": "",
            "match_type": "unverified",
            "status_tag": "待查证",
            "recommendation_reason": "该译法尚未关联已核对的原文。可使用带词检索入口继续查找，或点击「重新查证」获取官方词条。",
        })
    if result["source_blocked"]:
        result.update({"status_tag": "三级弱源·不可采信", "recommendation_reason": "此网站在既有清单中列为三级弱源，不能用于确认译法。请改用一级或交叉核对二级来源。"})
    return result

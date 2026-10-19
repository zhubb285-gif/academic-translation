"""Resolve source links without confusing a search page with an evidence page."""
from urllib.parse import parse_qs, urlencode, urlsplit


def search_link(url: str, term: str, candidate: str = "") -> dict:
    """Open the source's own search results with the term already entered."""
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or parsed.username:
            raise ValueError("Unsupported link")
    except ValueError:
        return {"search_url": "", "search_label": "", "search_term": ""}
    query = candidate or term
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
    else:
        # A guessed query parameter or a Google search is not an in-source search.
        return {"search_url": "", "search_label": "此信源暂未接入带词检索", "search_term": query}
    return {"search_url": target, "search_label": f"在{name}查看检索结果 ↗", "search_term": query}


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
    elif not path or path in ("/en", "/english", "/standards", "/SJ", "/obp"):
        url = "https://www.google.com/search?" + urlencode({"q": f'site:{host} "{candidate or term}"'})
    elif path in ("/search", "/search-results", "/search.html") or host in ("www.google.com", "google.com"):
        url = "https://www.google.com/search?" + urlencode({"q": f'site:{host} "{candidate or term}"'}) if host not in ("www.google.com", "google.com") else "https://www.google.com/search?" + urlencode({"q": candidate or term})
    else:
        return {"source_url": url, "link_kind": "entry", "link_label": "打开来源详情页 ↗"}
    return {"source_url": url, "link_kind": "search", "link_label": "带入此词检索（待核对）↗"}


def present_card(card: dict, term: str, trusted: bool = False) -> dict:
    """Old generated quotations must not be presented as retrieved original text."""
    result = dict(card)
    result.update(search_link(card.get("source_url", ""), term, card.get("recommended_translation", "")))
    result.update(source_link(card.get("source_url", ""), term, card.get("recommended_translation", "")))
    checked = trusted and result["link_kind"] == "entry" and bool(card.get("evidence_text"))
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
    return result

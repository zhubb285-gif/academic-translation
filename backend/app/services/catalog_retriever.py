"""Bounded retrieval from configured public source searches and their actual detail pages.

Search pages and model-generated suggestions never become quotations. Sites requiring
login, JavaScript or verification remain visible as unresolved human lookup tasks.
"""
import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import httpx


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links, self.skip = [], [], 0
        self.anchor = None
        self.paragraphs = []
        self.main_paragraphs = []
        self.paragraph = None
        self.content_depth = 0
        self.has_content_landmark = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form"):
            self.skip += 1
        if tag in ("main", "article"):
            self.content_depth += 1
            self.has_content_landmark = True
        if tag == "p" and not self.skip:
            self.paragraph = []
        if tag == "a" and not self.skip:
            self.anchor = [attrs.get("href", ""), ""]

    def handle_endtag(self, tag):
        if tag == "p" and self.paragraph is not None:
            text = re.sub(r"\s+", " ", " ".join(self.paragraph)).strip()
            if len(text.split()) >= 12:
                self.paragraphs.append(text)
                if self.content_depth:
                    self.main_paragraphs.append(text)
            self.paragraph = None
        if tag in ("main", "article"):
            self.content_depth = max(0, self.content_depth - 1)
        if tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form"):
            self.skip = max(0, self.skip - 1)
        if tag == "a" and self.anchor:
            self.links.append(tuple(self.anchor))
            self.anchor = None

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)
            if self.anchor:
                self.anchor[1] += text
            if self.paragraph is not None:
                self.paragraph.append(text)

    @property
    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def allowed(url: str, domains: list[str]) -> bool:
    try:
        value = urlsplit(url)
        host = (value.hostname or "").lower()
        return (value.scheme == "https" and not value.username and value.port in (None, 443)
                and any(host == d or host.endswith("." + d) for d in domains))
    except ValueError:
        return False


def is_detail(url: str) -> bool:
    value = urlsplit(url)
    # Never quote a search listing or an account/login endpoint as article evidence.
    return (len(value.path.rstrip("/")) > 5 and not re.search(
        r"search|query|results?|login|signin|register|account|captcha|verify", value.path + "?" + value.query, re.I))


async def fetch_page(client: httpx.AsyncClient, url: str, domains: list[str]) -> tuple[Page, str]:
    for _ in range(4):
        if not allowed(url, domains):
            raise ValueError("redirect_outside_source")
        # Stream and bound the body; PDF/raw-data assets are not part of term lookup.
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", ""):
                raise ValueError("non_html")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 1_500_000:
                    raise ValueError("page_too_large")
                chunks.append(chunk)
            page = Page()
            page.feed(b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"))
            if re.search(r"captcha|verify you are human|access denied|just a moment|enable javascript", page.text[:2500], re.I):
                raise ValueError("browser_verification_required")
            return page, url
    raise ValueError("too_many_redirects")


async def retrieve_level(catalogue: list[dict], level: int, term: str, candidates: list[str], exclude: set[str]) -> tuple[list[dict], list[dict]]:
    semaphore = asyncio.Semaphore(5)
    english = [c for c in candidates if c and not re.search(r"[\u4e00-\u9fff]", c)][:3]
    async with httpx.AsyncClient(timeout=httpx.Timeout(5), headers={"User-Agent": "AcademicTranslation-TermResearch/1.0"}) as client:
        async def lookup(source):
            trace = {"stage": f"tier{level}", "source": source["name"], "source_id": source["id"], "status": "manual_required"}
            links = [link for link in source["links"] if link.get("search_kind") == "internal" and link.get("search_url")]
            if not links:
                return [], trace
            # The declared search operator may use a dedicated subdomain of the source.
            link = links[0]
            search_host = urlsplit(link["search_url"]).hostname
            domains = list(dict.fromkeys([*source["domains"], search_host]))
            async with semaphore:
                try:
                    listing, search_url = await fetch_page(client, link["search_url"], domains)
                    ranked = []
                    for href, label in listing.links:
                        url = urljoin(search_url, href).split("#")[0]
                        if not allowed(url, domains) or not is_detail(url) or url in [v[1] for v in ranked]:
                            continue
                        score = int(term.casefold() in label.casefold()) * 2 + sum(c.casefold() in label.casefold() for c in english)
                        if score:
                            ranked.append((score, url))
                    entries = []
                    for _, url in sorted(ranked, reverse=True)[:2]:
                        try:
                            page, actual_url = await fetch_page(client, url, domains)
                        except (httpx.HTTPError, ValueError):
                            continue
                        for candidate in english:
                            quote = ""
                            for paragraph in page.main_paragraphs if page.has_content_landmark else page.paragraphs:
                                if re.search(r"log in|sign in|cookies|privacy policy|rights and permissions|access through your institution", paragraph, re.I):
                                    continue
                                match = re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", paragraph, re.I)
                                if match:
                                    quote = paragraph[max(0, match.start()-100):match.end()+220]
                                    break
                            if not quote:
                                continue
                            entries.append({"source_level": level, "source_name": source["name"], "source_type": "public_page_usage",
                                            "source_url": actual_url, "evidence_text": quote, "candidate_translation": candidate,
                                            "source_checked": True, "is_valid": True, "match_type": "english_usage", "evidence_group": "authority",
                                            "recommendation_reason": "已读取该信源详情页中的完整英文表达。词语出现不等于中英含义对应，必须由人工结合上下文核定。"})
                            break
                    trace["status"] = "found_usage" if entries else "no_verified_detail_match"
                    trace["count"] = len(entries)
                    return entries, trace
                except (httpx.HTTPError, ValueError) as exc:
                    trace["status"] = "unavailable"
                    trace["detail"] = type(exc).__name__
                    return [], trace
        results = await asyncio.gather(*(lookup(s) for s in catalogue if s["source_level"] == level and s["id"] not in exclude and not s["blocked"]))
    return [entry for entries, _ in results for entry in entries], [trace for _, trace in results]

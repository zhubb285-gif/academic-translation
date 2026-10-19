import unittest
import json
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.source_links import source_link, present_card, search_link
from app.services.source_research import SourceResearchService
from app.api.terminology import auto_research_term, _term_to_response
from app.models.database import Base, TerminologyEntry, SourceEvidence


OFFICIAL_GROUP = "00000000000000000000000000000000"
ENTRY = {
    "id": "2eb1048826ac11eea532b068e6519520",
    "cn": "海洋天然气水合物", "en": "marine gas hydrate",
    "definition": "分布于海洋的天然气水合物，通常见于水深大于500m的深海沉积物中。",
    "source": "海洋科技名词", "publishYear": "2007",
}


class SourceLinksTests(unittest.TestCase):
    def test_primary_button_opens_prefilled_source_search_even_when_entry_is_known(self):
        card = present_card({
            "source_url": "https://www.termonline.cn/wordDetail?termName=word&subject=123&base=1",
            "recommended_translation": "marine gas hydrate", "evidence_text": "real source text",
        }, "海洋天然气水合物", trusted=True)
        parsed = urlsplit(card["search_url"])
        self.assertEqual(parsed.hostname, "www.termonline.cn")
        self.assertEqual(parsed.path, "/search")
        self.assertEqual(parse_qs(parsed.query), {"searchText": ["海洋天然气水合物"]})
        self.assertIn("wordDetail", card["source_url"])

    def test_nature_search_is_within_the_source_and_uses_the_english_phrase(self):
        link = search_link("https://www.nature.com", "海洋天然气水合物", "Marine Gas Hydrate")
        self.assertEqual(link["search_url"], "https://www.nature.com/search?q=Marine+Gas+Hydrate")

    def test_old_term_search_uses_current_parameter_and_chinese_term(self):
        link = source_link("https://www.termonline.cn/search?k=natural%20gas%20hydrate", "海洋天然气水合物")
        self.assertEqual(parse_qs(urlsplit(link["source_url"]).query), {"searchText": ["海洋天然气水合物"]})
        self.assertEqual(link["link_kind"], "search")

    def test_nature_homepage_searches_candidate_without_retyping(self):
        link = source_link("https://www.nature.com", "海洋天然气水合物", "Marine Gas Hydrate")
        self.assertEqual(parse_qs(urlsplit(link["source_url"]).query)["q"], ["Marine Gas Hydrate"])
        self.assertEqual(link["link_kind"], "search")

    def test_legacy_generated_quote_is_not_a_verified_source(self):
        card = present_card({"source_url": "https://www.nature.com", "recommended_translation": "Marine Gas Hydrate", "evidence_text": "Technical studies also widely reference...", "match_type": "exact"}, "海洋天然气水合物")
        self.assertFalse(card["source_checked"])
        self.assertEqual(card["evidence_text"], "")
        self.assertEqual(card["status_tag"], "待查证")

    def test_unsafe_link_is_not_rendered(self):
        self.assertEqual(source_link("javascript:alert(1)", "词")["source_url"], "")


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def lookup(self, groups, fail=False):
        calls = []
        def handler(request):
            calls.append(request)
            if fail:
                raise httpx.ConnectError("offline", request=request)
            if request.url.path.endswith("listFront"):
                return httpx.Response(200, json={"success": True, "result": []})
            return httpx.Response(200, json={"success": True, "result": {"searchResult": groups}})
        client_class = httpx.AsyncClient
        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(handler), **kwargs)
        with patch("app.services.source_research.httpx.AsyncClient", side_effect=make_client):
            result = await SourceResearchService()._lookup_official("海洋天然气水合物")
        return result, calls

    async def test_retrieved_entry_links_to_its_id_and_preserves_real_text(self):
        result, calls = await self.lookup([{"id": OFFICIAL_GROUP, "result": {"tmWordList": [ENTRY]}}])
        entry = result["entries"][0]
        self.assertEqual(result["status"], "found")
        self.assertIn(ENTRY["definition"], entry["evidence_text"])
        query = parse_qs(urlsplit(entry["source_url"]).query)
        self.assertEqual(query["subject"], [ENTRY["id"]])
        self.assertEqual(query["termName"], [ENTRY["cn"]])
        self.assertTrue(calls[0].url.path.endswith("listFront"))

    async def test_partial_match_and_consultation_database_are_not_official_exact_matches(self):
        result, _ = await self.lookup([
            {"id": OFFICIAL_GROUP, "result": {"tmWordList": [{**ENTRY, "cn": "天然气水合物"}]}},
            {"id": "00000000000000000000000000000006", "result": {"tmWordList": [ENTRY]}},
        ])
        self.assertEqual(result, {"status": "no_exact_match", "entries": []})

    async def test_unavailable_source_is_not_reported_as_missing_term(self):
        result, _ = await self.lookup([], fail=True)
        self.assertEqual(result, {"status": "unavailable", "entries": []})

    async def test_complete_entry_stops_before_decomposition(self):
        service = SourceResearchService()
        entry = {"source_level": 1, "source_url": "https://www.termonline.cn/wordDetail?termName=word&subject=123&base=1", "candidate_translation": "marine gas hydrate", "evidence_text": "real original"}
        service._lookup_official = AsyncMock(return_value={"status": "found", "entries": [entry]})
        service.step2_semantic_decompose = AsyncMock()
        result = await service.execute_progressive_research("海洋天然气水合物")
        self.assertTrue(result["is_exact"])
        service.step2_semantic_decompose.assert_not_awaited()
        self.assertEqual(len(result["cards"]), 1)

    async def test_core_entry_does_not_verify_the_full_phrase(self):
        service = SourceResearchService()
        core = {"source_level": 1, "source_url": "https://www.termonline.cn/wordDetail?termName=core&subject=1&base=1", "candidate_translation": "gas hydrate", "evidence_text": "real core definition"}
        service._lookup_official = AsyncMock(side_effect=[{"status": "no_exact_match", "entries": []}, {"status": "found", "entries": [core]}])
        service.step2_semantic_decompose = AsyncMock(return_value={"core_term": "天然气水合物", "combined_translation": "deepwater gas hydrate", "components": []})
        result = await service.execute_progressive_research("深水天然气水合物")
        self.assertFalse(result["is_exact"])
        self.assertEqual(result["cards"][0]["match_type"], "core_only")
        self.assertFalse(result["cards"][1]["source_checked"])
        self.assertEqual(result["cards"][1]["evidence_text"], "")


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_survives_reload_without_overwriting_user_decision_or_duplicate_records(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            term = TerminologyEntry(project_id=1, source_term=ENTRY["cn"], status="confirmed", confirmed_translation="User's chosen translation")
            db.add(term)
            db.commit()
            entry = {
                "source_level": 1, "source_url": "https://www.termonline.cn/wordDetail?termName=word&subject=123&base=1",
                "candidate_translation": ENTRY["en"], "evidence_text": ENTRY["definition"], "source_checked": True,
            }
            card = {**entry, "recommended_translation": ENTRY["en"], "match_type": "exact"}
            result = {"source_verification_version": 2, "is_exact": True, "candidates": [ENTRY["en"]], "cards": [card], "evidences": [entry]}
            with patch("app.api.terminology.source_research_service.execute_progressive_research", AsyncMock(return_value=result)):
                await auto_research_term(term.id, db)
                await auto_research_term(term.id, db)
            db.expire_all()
            response = _term_to_response(db.get(TerminologyEntry, term.id), db)
            self.assertEqual(db.query(SourceEvidence).count(), 1)
            self.assertTrue(response["cards"][0]["source_checked"])
            self.assertEqual(response["cards"][0]["link_kind"], "entry")
            self.assertEqual(response["confirmed_translation"], "User's chosen translation")
        engine.dispose()

    async def test_legacy_database_record_gets_safe_links_before_rerunning_search(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            term = TerminologyEntry(project_id=1, source_term=ENTRY["cn"], notes=json.dumps({"cards": [{
                "recommended_translation": "Marine Gas Hydrate", "source_url": "https://www.nature.com", "evidence_text": "invented old quotation", "match_type": "exact",
            }]}))
            db.add(term)
            db.commit()
            response = _term_to_response(term, db)
            card = response["cards"][0]
            self.assertFalse(card["source_checked"])
            self.assertEqual(card["evidence_text"], "")
            self.assertEqual(parse_qs(urlsplit(card["source_url"]).query)["q"], ["Marine Gas Hydrate"])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()

import unittest
import json
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.source_links import source_link, present_card, search_link
from app.services.source_research import SourceResearchService
from app.api.terminology import auto_research_term, _term_to_response, add_evidence, list_evidence, verify_evidence, get_term_sources
from app.models.database import Base, TerminologyEntry, SourceEvidence
from app.schemas.schemas import EvidenceCreate, EvidenceResponse
from app.services.source_catalog import SOURCES, find_source, source_catalog


OFFICIAL_GROUP = "00000000000000000000000000000000"
ENTRY = {
    "id": "2eb1048826ac11eea532b068e6519520",
    "cn": "海洋天然气水合物", "en": "marine gas hydrate",
    "definition": "分布于海洋的天然气水合物，通常见于水深大于500m的深海沉积物中。",
    "source": "海洋科技名词", "publishYear": "2007",
}


class SourceLinksTests(unittest.TestCase):
    def test_silkroad_search_uses_the_actual_encoded_route_and_correct_institution(self):
        link = search_link("https://www.imsilkroad.com/", "石油", "petroleum")
        self.assertEqual(link["search_url"], "https://www.imsilkroad.com/search/all/1/JUU3JTlGJUIzJUU2JUIyJUI5")
        self.assertEqual(link["search_term"], "石油")
        self.assertEqual(find_source("", "国新办丝路网")["name"], "新华丝路")

    def test_search_does_not_silently_switch_to_another_government_website(self):
        for url in ("https://english.scio.gov.cn/", "https://example.gov.cn/", "https://www.google.com/search?q=old"):
            with self.subTest(url=url):
                link = search_link(url, "石油", "petroleum")
                self.assertEqual(link["search_kind"], "unavailable")
                self.assertEqual(link["search_url"], "")
                self.assertEqual(source_link(url, "石油", "petroleum")["source_url"], "")

    def test_all_original_categories_are_present_with_honest_usable_links(self):
        catalog = source_catalog("水力压裂", "hydraulic fracturing")
        for level, count in ((1, 9), (2, 20), (3, 11)):
            self.assertEqual(len([s for s in catalog if s["origin"] == "既有信源清单" and s["source_level"] == level]), count)
        for source in catalog:
            with self.subTest(source=source["id"]):
                self.assertEqual(len(source["links"]), len(source["domains"]))
                for link in source["links"]:
                    self.assertTrue(link["url"].startswith("https://"))
                    if source["blocked"]:
                        self.assertEqual(link["search_url"], "")
                    elif link["search_kind"] == "internal":
                        self.assertTrue(link["search_url"])
                        self.assertNotIn(urlsplit(link["search_url"]).hostname, ("www.google.com", "www.bing.com"))
                    else:
                        self.assertEqual(link["search_kind"], "unavailable")
                        self.assertEqual(link["search_url"], "")
        self.assertEqual(find_source("https://www.sciencedirect.com/science/article/123")["source_level"], 2)

    def test_specific_domain_wins_and_lookalike_domains_do_not_inherit_trust(self):
        self.assertEqual(find_source("https://en.moe.gov.cn/article/1")["id"], "T1-02")
        self.assertIsNone(find_source("https://termonline.cn.evil.example/"))
        english = search_link("https://english.www.gov.cn", "石油", "petroleum")
        self.assertEqual(urlsplit(english["search_url"]).hostname, "search.english.www.gov.cn")
        self.assertEqual(parse_qs(urlsplit(english["search_url"]).query)["searchWord"], ["petroleum"])

    def test_unconnected_source_never_offers_external_search_or_homepage_as_search(self):
        link = search_link("https://onepetro.org/article/123", "压裂", "hydraulic fracturing")
        self.assertEqual(link["search_kind"], "unavailable")
        self.assertIn("暂未接通", link["search_label"])
        self.assertEqual(link["search_url"], "")

    def test_xinhua_and_osti_search_paths_fill_current_terms_without_exact_phrase_quotes(self):
        for term, english in (("全国脱贫攻坚楷模", "National Model for Poverty Alleviation"),
                              ("水力压裂", "hydraulic fracturing"),
                              ("钠离子与α相", "Na+ & α-phase / 50%")):
            from urllib.parse import unquote
            for domain in ("www.xinhuanet.com", "english.news.cn", "www.osti.gov"):
                with self.subTest(term=term, domain=domain):
                    link = search_link("https://" + domain + "/", term, english)
                    self.assertEqual(link["search_kind"], "internal")
                    self.assertEqual(link["search_term"], english)
                    self.assertIn(english, unquote(link["search_url"]))
                    self.assertNotIn('"', unquote(link["search_url"]))

    def test_national_standard_and_china_daily_use_their_actual_search_parameters(self):
        standard = search_link("https://openstd.samr.gov.cn/bzgk/gb/", "石油", "petroleum")
        self.assertEqual(parse_qs(urlsplit(standard["search_url"]).query)["p.p2"], ["石油"])
        daily = search_link("https://www.chinadaily.com.cn/", "石油", "petroleum")
        self.assertEqual(urlsplit(daily["search_url"]).hostname, "newssearch.chinadaily.com.cn")
        self.assertEqual(parse_qs(urlsplit(daily["search_url"]).query)["query"], ["petroleum"])

    def test_missing_url_can_be_repaired_from_known_source_name_without_faking_evidence(self):
        card = present_card({"source_name": "SPE OnePetro", "recommended_translation": "hydraulic fracturing", "source_level": 3}, "水力压裂")
        self.assertEqual(card["source_level"], 2)
        self.assertEqual(card["source_name"], "SPE OnePetro")
        self.assertEqual(card["search_url"], "")
        self.assertEqual(card["search_kind"], "unavailable")
        self.assertFalse(card["source_checked"])

    def test_weak_source_cannot_be_presented_as_verified_even_if_old_metadata_says_so(self):
        card = present_card({"source_url": "https://baike.baidu.com/item/123", "source_level": 1,
                             "evidence_text": "old claim", "source_checked": True}, "水力压裂", trusted=True)
        self.assertEqual(card["source_level"], 3)
        self.assertTrue(card["source_blocked"])
        self.assertFalse(card["source_checked"])
        self.assertEqual(card["search_url"], "")

    def test_each_registered_source_uses_the_current_term_including_special_characters(self):
        sources = [
            ("https://www.termonline.cn/search?searchText=old", "searchText", True),
            ("https://www.nature.com", "q", False),
            ("https://www.iso.org/obp", "q", False),
            ("https://ieeexplore.ieee.org", "queryText", False),
            ("https://dl.acm.org", "AllField", False),
            ("https://www.ncbi.nlm.nih.gov/mesh", "term", False),
        ]
        terms = [
            ("水力压裂", "hydraulic fracturing"),
            ("注意力机制", "attention mechanism"),
            ("生命周期评价", "Life Cycle Assessment (LCA)"),
            ("钠离子与α相", "Na+ & α-phase / 50%"),
        ]
        for source, parameter, chinese in sources:
            for term, translation in terms:
                with self.subTest(source=source, term=term):
                    card = present_card({"source_url": source, "recommended_translation": translation}, term)
                    self.assertEqual(parse_qs(urlsplit(card["search_url"]).query)[parameter], [term if chinese else translation])
                    self.assertEqual(card["search_term"], term if chinese else translation)

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
        with patch("app.services.source_research.search_usage", return_value=[]):
            result = await service.execute_progressive_research("海洋天然气水合物", candidates=["marine gas hydrate"])
        self.assertTrue(result["is_exact"])
        service.step2_semantic_decompose.assert_not_awaited()
        self.assertEqual(len(result["cards"]), 1)

    async def test_core_entry_does_not_verify_the_full_phrase(self):
        service = SourceResearchService()
        core = {"source_level": 1, "source_url": "https://www.termonline.cn/wordDetail?termName=core&subject=1&base=1", "candidate_translation": "gas hydrate", "evidence_text": "real core definition"}
        service._lookup_official = AsyncMock(side_effect=[{"status": "no_exact_match", "entries": []}, {"status": "found", "entries": [core]}])
        service.step2_semantic_decompose = AsyncMock(return_value={"core_term": "天然气水合物", "combined_translation": "deepwater gas hydrate", "components": []})
        service._lookup_secondary = AsyncMock(return_value={"status": "no_exact_match", "entries": []})
        with patch("app.services.source_research.search_usage", return_value=[]), patch("app.services.source_research.retrieve_level", AsyncMock(return_value=([], []))):
            result = await service.execute_progressive_research("深水天然气水合物")
        self.assertFalse(result["is_exact"])
        self.assertEqual(result["cards"][0]["match_type"], "core_only")
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["recommended_translation"], "")
        self.assertIn("deepwater gas hydrate", result["candidates"])
        self.assertTrue(result["requires_human_decision"])


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_endpoint_and_manual_evidence_follow_the_same_source_policy(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            term = TerminologyEntry(project_id=1, source_term="注意力机制")
            db.add(term)
            db.commit()
            result = get_term_sources(term.id, "attention mechanism", db)
            self.assertEqual(len(result["sources"]), len(SOURCES))
            with self.assertRaises(HTTPException) as error:
                add_evidence(term.id, EvidenceCreate(source_level=1, source_url="https://en.wikipedia.org/wiki/Attention"), db)
            self.assertEqual(error.exception.status_code, 400)
            saved = add_evidence(term.id, EvidenceCreate(source_level=1, source_url="https://onepetro.org/article/1"), db)
            self.assertEqual(saved["source_level"], 2)
            old = SourceEvidence(term_id=term.id, source_level=1, source_url="https://baike.baidu.com/item/1")
            db.add(old)
            db.commit()
            with self.assertRaises(HTTPException):
                verify_evidence(old.id, True, "user", db)
        engine.dispose()

    async def test_manual_evidence_links_work_immediately_and_after_reload_for_each_term(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            for source_term in ("水力压裂", "注意力机制", "生命周期评价"):
                with self.subTest(term=source_term):
                    term = TerminologyEntry(project_id=1, source_term=source_term)
                    db.add(term)
                    db.commit()
                    # A pasted URL may still contain a previous search term.
                    response = add_evidence(term.id, EvidenceCreate(
                        source_level=1, source_url="https://www.termonline.cn/search?searchText=old",
                        candidate_translation="candidate",
                    ), db)
                    immediate = EvidenceResponse.model_validate(response).model_dump()
                    reloaded = _term_to_response(term, db)
                    listed = list_evidence(term.id, db)
                    for evidence in (immediate, reloaded["evidence"][0], listed[0], reloaded["cards"][0]):
                        self.assertEqual(parse_qs(urlsplit(evidence["search_url"]).query), {"searchText": [source_term]})
        engine.dispose()

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

import hashlib
import json
import re
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.journal_library import CATALOG, SKILLS, articles, search_usage, style_skill
from app.services.source_research import SourceResearchService
from app.services.catalog_retriever import retrieve_level, allowed
from app.services.translation_service import build_translation_prompt
from app.api.terminology import auto_research_term, confirm_term, _term_to_response, verify_evidence
from app.api.projects import update_project
from app.models.database import Base, Project, Journal, TerminologyEntry, SourceEvidence
from app.schemas.schemas import ProjectUpdate


class LibraryTests(unittest.TestCase):
    def test_corpus_has_real_text_per_journal_and_hashes_match(self):
        rows = articles()
        self.assertEqual(len({a['doi'] for a in rows}), len(rows))
        for journal in CATALOG['journals']:
            own = [a for a in rows if a['journal_slug'] == journal['slug']]
            self.assertGreaterEqual(len(own), 10, journal['name'])
            self.assertTrue((SKILLS / journal['slug'] / 'SKILL.md').is_file())
        for row in rows:
            self.assertRegex(row['doi'], r'^10\.\d{4,9}/')
            self.assertNotIn('example', row['doi'])
            text = '\n'.join(row['paragraphs'])
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), row['text_sha256'])
            self.assertTrue(row['text_source_url'].startswith('https://'))

    def test_usage_requires_whole_phrase_and_does_not_invent_bilingual_correspondence(self):
        hits = search_usage('水力压裂', ['hydraulic fracturing'], '石油工程', 'SPE Journal')
        self.assertTrue(hits)
        self.assertEqual(hits[0]['journal'], 'SPE Journal')
        self.assertTrue(all(h['match_type'] == 'english_usage' for h in hits))
        self.assertTrue(all(re.search(r'hydraulic[\s\-–]+fracturing', h['evidence_text'], re.I) for h in hits))
        self.assertEqual(search_usage('不存在的测试术语', ['a made up phrase never written 84952381']), [])
        self.assertEqual(search_usage('生产关系', ['production'], '马克思主义理论'), [])
        self.assertEqual(search_usage('责任', ['liability'], '法学'), [])

    def test_selected_skill_is_injected_and_switch_disables_it(self):
        journal = {'name': 'SPE Journal', 'style_skill_enabled': True}
        enabled = build_translation_prompt('本文研究储层。', 'S001', 'Methods', journal)
        self.assertIn('translate-spe-journal', enabled)
        self.assertIn('不把 Methods 改写成摘要', enabled)
        disabled = build_translation_prompt('本文研究储层。', 'S001', 'Methods', {**journal, 'style_skill_enabled': False})
        self.assertNotIn('translate-spe-journal', disabled)
        self.assertEqual(style_skill('SPE Journal')['article_count'], sum(a['journal'] == 'SPE Journal' for a in articles()))

    def test_project_can_clear_journal_and_disable_skill(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            journal = Journal(name='SPE Journal')
            db.add(journal)
            db.flush()
            project = Project(name='Test', journal_id=journal.id)
            db.add(project)
            db.commit()
            updated = update_project(project.id, ProjectUpdate(journal_id=None, style_skill_enabled=False), db)
            self.assertIsNone(updated.journal_id)
            self.assertFalse(updated.style_skill_enabled)
        engine.dispose()


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_editable_notes_cannot_forge_retrieved_original_text(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            forged = {'source_verification_version': 3, 'cards': [{'source_url': 'https://doi.org/10.2118/204210-PA',
                      'recommended_translation': 'hydraulic fracturing', 'source_checked': True,
                      'evidence_text': 'This fabricated quotation was not retrieved.', 'evidence_group': 'journal'}]}
            term = TerminologyEntry(project_id=1, source_term='水力压裂', notes=json.dumps(forged))
            db.add(term)
            db.commit()
            response = _term_to_response(term, db)
            self.assertFalse(response['journal_cards'][0]['source_checked'])
            self.assertEqual(response['journal_cards'][0]['evidence_text'], '')
        engine.dispose()

    async def test_same_spelling_in_another_discipline_does_not_stop_fallback(self):
        service = SourceResearchService()
        entry = {'source_level': 1, 'candidate_translation': 'hydraulic fracturing',
                 'source_name': '全国科学技术名词审定委员会 · 冶金学名词', 'evidence_text': '冶金领域定义'}
        service._lookup_official = AsyncMock(return_value={'status': 'found', 'entries': [entry]})
        service._lookup_secondary = AsyncMock(return_value={'status': 'no_exact_match', 'entries': []})
        with patch('app.services.source_research.search_usage', return_value=[]), patch('app.services.source_research.retrieve_level', AsyncMock(return_value=([], []))):
            result = await service.execute_progressive_research('水力压裂', '石油与天然气工程')
        self.assertFalse(result['is_exact'])
        self.assertEqual(result['authority_cards'][0]['match_type'], 'domain_mismatch')
        self.assertEqual(result['lookup_trace'][1]['status'], 'found_other_domain')
        service._lookup_secondary.assert_awaited_once()

    async def test_journal_first_then_tier1_even_on_journal_hit_and_no_tier2_when_exact(self):
        events = []
        journal = {'candidate_translation': 'hydraulic fracturing', 'recommended_translation': 'hydraulic fracturing'}
        official = {'source_level': 1, 'candidate_translation': 'hydraulic fracturing', 'source_url': 'https://www.termonline.cn/wordDetail?subject=1&termName=x', 'evidence_text': '真实双语词条'}
        def usage(*args):
            events.append('journal')
            return [journal]
        async def official_lookup(term):
            events.append('tier1')
            return {'status': 'found', 'entries': [official]}
        service = SourceResearchService()
        service._lookup_official = official_lookup
        service._lookup_secondary = AsyncMock()
        with patch('app.services.source_research.search_usage', side_effect=usage), patch('app.services.source_research.retrieve_level', AsyncMock()) as retrieve:
            result = await service.execute_progressive_research('水力压裂')
        self.assertEqual(events[:2], ['journal', 'tier1'])
        self.assertEqual(result['comparison_status'], 'agreement')
        self.assertTrue(result['requires_human_decision'])
        service._lookup_secondary.assert_not_awaited()
        retrieve.assert_not_awaited()
        self.assertTrue(any(t['status'] == 'excluded' for t in result['lookup_trace']))

    async def test_tier1_unavailable_is_not_claimed_missing_and_tier2_still_separate(self):
        service = SourceResearchService()
        service._lookup_official = AsyncMock(return_value={'status': 'unavailable', 'entries': []})
        service.step2_semantic_decompose = AsyncMock(return_value={'core_term': '水力压裂', 'components': []})
        service._lookup_secondary = AsyncMock(return_value={'status': 'no_exact_match', 'entries': []})
        calls = []
        async def retrieve(catalogue, level, *args):
            calls.append(level)
            self.assertTrue(all(s['source_level'] < 3 for s in catalogue if s['source_level'] == level))
            return [], []
        with patch('app.services.source_research.retrieve_level', side_effect=retrieve), patch('app.services.source_research.search_usage', return_value=[]):
            result = await service.execute_progressive_research('水力压裂')
        self.assertEqual(calls, [1, 2])
        self.assertEqual(result['lookup_trace'][1]['status'], 'unavailable')
        self.assertEqual(result['comparison_status'], 'no_evidence')

    async def test_persistence_human_decision_history_and_research_does_not_overwrite_choice(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            term = TerminologyEntry(project_id=1, source_term='水力压裂', notes='用户备注')
            db.add(term)
            db.commit()
            card = {'candidate_translation': 'hydraulic fracturing', 'recommended_translation': 'hydraulic fracturing', 'source_level': 2,
                    'source_type': 'journal_usage', 'evidence_group': 'journal', 'source_url': 'https://doi.org/10.2118/204210-PA',
                    'evidence_text': 'Hydraulic fracturing is used in this real-text test fixture.', 'source_checked': True, 'match_type': 'english_usage'}
            result = {'source_verification_version': 3, 'candidates': ['hydraulic fracturing'], 'cards': [card], 'evidences': [card]}
            with patch('app.api.terminology.source_research_service.execute_progressive_research', AsyncMock(return_value=result)):
                await auto_research_term(term.id, db)
                self.assertNotEqual(term.status, 'confirmed')
                confirm_term(term.id, 'hydraulic fracturing', db, reason='符合储层改造语境')
                await auto_research_term(term.id, db)
            response = _term_to_response(db.get(TerminologyEntry, term.id), db)
            self.assertEqual(response['confirmed_translation'], 'hydraulic fracturing')
            self.assertEqual(response['research_summary']['user_notes'], '用户备注')
            self.assertEqual(len(response['research_summary']['human_decisions']), 1)
            self.assertEqual(response['research_summary']['human_decisions'][0]['evidence_snapshot'][0]['source_level'], 2)
            self.assertEqual(db.query(SourceEvidence).count(), 1)
            self.assertTrue(response['journal_cards'][0]['source_checked'])
            verify_evidence(db.query(SourceEvidence).first().id, False, 'user', db)
            self.assertFalse(_term_to_response(term, db)['journal_cards'][0]['source_checked'])
        engine.dispose()

    async def test_search_page_is_not_evidence_and_redirect_cannot_leave_source(self):
        self.assertFalse(allowed('https://official.example.evil.com/page', ['official.example']))
        self.assertFalse(allowed('http://official.example/page', ['official.example']))
        def handler(request):
            if request.url.path == '/search':
                return httpx.Response(200, text='hydraulic fracturing <a href="/article/real">hydraulic fracturing study</a>', headers={'content-type': 'text/html'})
            return httpx.Response(302, headers={'location': 'https://evil.example/private'})
        real_client = httpx.AsyncClient
        def mock_client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        source = {'id': 'test', 'source_level': 1, 'name': 'Test source', 'blocked': False, 'domains': ['official.example'],
                  'links': [{'search_kind': 'internal', 'search_url': 'https://official.example/search?q=hydraulic'}]}
        with patch('app.services.catalog_retriever.httpx.AsyncClient', side_effect=mock_client):
            entries, trace = await retrieve_level([source], 1, '水力压裂', ['hydraulic fracturing'], set())
        self.assertEqual(entries, [])
        self.assertEqual(trace[0]['status'], 'no_verified_detail_match')

    async def test_navigation_and_page_title_are_not_quoted_as_article_body(self):
        def handler(request):
            content = '<a href="/article/real">hydraulic fracturing study</a>' if request.url.path == '/search' else '<main><h1>Hydraulic fracturing study</h1><nav><p>This navigation mentions hydraulic fracturing but is not the actual scientific content of the page.</p></nav><p>This article contains unrelated prose about sedimentary deposits and their regional structure, without the queried technical phrase.</p></main>'
            return httpx.Response(200, text=content, headers={'content-type': 'text/html'})
        real_client = httpx.AsyncClient
        source = {'id': 'test', 'source_level': 1, 'name': 'Test', 'blocked': False, 'domains': ['official.example'], 'links': [{'search_kind': 'internal', 'search_url': 'https://official.example/search?q=hydraulic'}]}
        with patch('app.services.catalog_retriever.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            entries, _ = await retrieve_level([source], 1, '水力压裂', ['hydraulic fracturing'], set())
        self.assertEqual(entries, [])


if __name__ == '__main__':
    unittest.main()

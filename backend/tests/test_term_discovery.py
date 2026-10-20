import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, Project, Document, Segment, TerminologyEntry
from app.services.term_discovery import make_chunks, parse_candidates, resolve_model, run_document_discovery, queue_document, interrupt_stale_jobs
from app.api.term_discovery import discovery_status, start_discovery, DiscoveryRequest
from app.api.documents import parse_document_task


class CandidateTests(unittest.TestCase):
    def test_all_text_is_covered_and_cut_terms_have_overlap(self):
        source = '甲' * 3197 + '水力压裂' + '乙' * 4000
        chunks = make_chunks([Segment(segment_id='S001', source_text=source)])
        self.assertTrue(any('水力压裂' in part['text'] for chunk in chunks for part in chunk))
        self.assertTrue(chunks[-1][-1]['text'].endswith('乙' * 100))
        self.assertGreater(len(chunks), 1)

    def test_hallucinations_and_split_phrase_are_not_saved_as_terms(self):
        chunk = [{'segment_id': 'S007', 'text': '水力压裂可改造储层。'}]
        raw = json.dumps({'terms': [
            {'term': '水力压裂', 'reason': '储层改造技术', 'candidate_translations': ['hydraulic fracturing']},
            {'term': '水力压裂'}, {'term': '不存在的词'}, {'term': '水力储层'}, {'term': '水力压裂。'}]})
        result = parse_candidates(raw, chunk, '石油工程')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['occurrences'][0]['segment_id'], 'S007')
        self.assertEqual(result[0]['domain'], '石油工程')
        with self.assertRaises(ValueError):
            parse_candidates('not json', chunk)

    def test_no_demo_output_when_key_is_missing(self):
        with patch('app.services.term_discovery.settings') as config:
            config.default_translation_provider = 'deepseek'
            config.deepseek_api_key = ''
            with self.assertRaises(ValueError):
                resolve_model(Project(translation_provider='deepseek'))


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        with self.factory() as db:
            p = Project(name='test', domain='石油工程', translation_provider='deepseek', translation_model='deepseek-chat')
            db.add(p); db.flush()
            d = Document(project_id=p.id, filename='test.txt', original_filename='test.txt', file_type='txt', file_path='unused', parse_status='done')
            db.add(d); db.flush()
            db.add(Segment(project_id=p.id, document_id=d.id, segment_id='S001', order_index=0, source_text='水力压裂提高储层采收率。'))
            db.commit()
            self.pid, self.did = p.id, d.id
        self.sessions = patch('app.services.term_discovery.SessionLocal', self.factory)
        self.sessions.start()
        self.model = patch('app.services.term_discovery.resolve_model', return_value=('deepseek', 'deepseek-chat'))
        self.model.start()

    def tearDown(self):
        self.model.stop(); self.sessions.stop(); self.engine.dispose()

    async def test_discovery_precedes_research_and_research_keeps_grounded_origin(self):
        events = []
        async def extract(chunk, *args):
            events.append('AI')
            return parse_candidates('{"terms":[{"term":"水力压裂","reason":"储层改造技术","candidate_translations":["hydraulic fracturing"]}]}', chunk, '石油工程')
        async def research(**kwargs):
            events.append('journal-and-authorities')
            self.assertIn('水力压裂提高储层', kwargs['context'])
            return {'source_verification_version': 3, 'cards': [], 'evidences': [], 'candidates': ['hydraulic fracturing']}
        with self.factory() as db:
            self.assertTrue(queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat'))
            self.assertFalse(queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat'))
        with patch('app.services.term_discovery.extract_chunk', side_effect=extract), patch('app.api.terminology.source_research_service.execute_progressive_research', side_effect=research):
            await run_document_discovery(self.did)
        self.assertEqual(events, ['AI', 'journal-and-authorities'])
        with self.factory() as db:
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'done')
            t = db.query(TerminologyEntry).one()
            self.assertEqual(t.status, 'pending')
            self.assertIsNone(t.confirmed_translation)
            origin = json.loads(t.notes)['ai_extraction'][0]
            self.assertEqual(origin['document_id'], self.did)
            self.assertIn('水力压裂', origin['context'])

    async def test_retry_resumes_failed_research_without_duplicate_or_losing_manual_choice(self):
        with self.factory() as db:
            term = TerminologyEntry(project_id=self.pid, source_term='水力压裂', status='confirmed', confirmed_translation='my manual choice')
            db.add(term); db.commit()
            confirmed_id = term.id
            queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat')
        chunk = [{'segment_id': 'S001', 'text': '水力压裂提高储层采收率。'}]
        candidates = parse_candidates('{"terms":[{"term":"水力压裂"},{"term":"储层"}]}', chunk)
        with patch('app.services.term_discovery.extract_chunk', AsyncMock(return_value=candidates)), patch('app.api.terminology.auto_research_term', AsyncMock(side_effect=RuntimeError('failure'))):
            await run_document_discovery(self.did)
        with self.factory() as db:
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'partial')
            queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat')
        with patch('app.services.term_discovery.extract_chunk', AsyncMock()) as extract, patch('app.api.terminology.auto_research_term', AsyncMock()) as research:
            await run_document_discovery(self.did)
            extract.assert_not_awaited()
            research.assert_awaited_once()
        with self.factory() as db:
            self.assertEqual(db.query(TerminologyEntry).count(), 2)
            self.assertEqual(db.get(TerminologyEntry, confirmed_id).confirmed_translation, 'my manual choice')
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'done')

    async def test_restart_and_model_failure_are_recoverable_and_not_fake_success(self):
        with self.factory() as db:
            queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat')
        interrupt_stale_jobs()
        with self.factory() as db:
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'interrupted')
            queue_document(db, db.get(Document, self.did), 'deepseek', 'deepseek-chat')
        with patch('app.services.term_discovery.extract_chunk', AsyncMock(side_effect=ValueError('bad model output'))):
            await run_document_discovery(self.did)
        with self.factory() as db:
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'error')
            self.assertEqual(db.query(TerminologyEntry).count(), 0)

    async def test_parse_triggers_discovery_and_has_its_own_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.txt'
            path.write_text('本文采用水力压裂技术提高储层采收率。', encoding='utf-8')
            with patch('app.api.documents.SessionLocal', self.factory), patch('app.services.term_discovery.run_document_discovery', AsyncMock()) as run:
                await parse_document_task(str(path), self.did, self.pid)
                run.assert_awaited_once_with(self.did)
        with self.factory() as db:
            self.assertEqual(db.get(Document, self.did).parse_status, 'done')
            self.assertEqual(db.get(Document, self.did).terminology_analysis['status'], 'queued')

    async def test_old_documents_can_be_started_and_progress_has_no_secrets(self):
        with self.factory() as db:
            with patch('app.api.term_discovery.resolve_model', return_value=('deepseek', 'deepseek-chat')):
                tasks = BackgroundTasks()
                result = start_discovery(self.pid, DiscoveryRequest(), tasks, db)
                self.assertEqual(result['queued_document_ids'], [self.did])
                again = start_discovery(self.pid, DiscoveryRequest(), BackgroundTasks(), db)
                self.assertEqual(again['queued_document_ids'], [])
                status = discovery_status(self.pid, db)
                self.assertEqual(status['documents'][0]['analysis']['status'], 'queued')
                self.assertNotIn('api_key', json.dumps(status))

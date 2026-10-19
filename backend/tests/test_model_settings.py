"""Editing a model must preserve its identity and leave other models unchanged."""
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.other import models_router
from app.core.database import get_db
from app.models.database import Base, ModelConfig

class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            ModelConfig(name='Original', provider='custom', model_id='model-a', api_base_url='https://example.org/v1', context_window=8000, cost_per_1k_input=0.1),
            ModelConfig(name='Other model', provider='deepseek', model_id='deepseek-chat'),
        ])
        self.db.commit()
        self.first_id, self.other_id = [c.id for c in self.db.query(ModelConfig).order_by(ModelConfig.id).all()]
        app = FastAPI()
        app.include_router(models_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_edit_preserves_identity_and_clears_optional_settings(self):
        response = self.client.put(f'/models/{self.first_id}', json={
            'name': 'Edited model', 'provider': 'custom', 'model_id': 'model-b',
            'api_base_url': None, 'context_window': None, 'cost_per_1k_input': None,
            'capabilities': ['术语核对'], 'use_for_translation': False,
            'use_for_proofreading': True, 'supports_json_mode': False,
        })
        self.assertEqual(response.status_code, 200, response.text)
        model = response.json()
        self.assertEqual(model['id'], self.first_id)
        self.assertEqual(model['model_id'], 'model-b')
        self.assertFalse(model['use_for_translation'])
        for key in ('api_base_url', 'cost_per_1k_input', 'context_window'):
            self.assertIsNone(model[key])
        self.assertEqual(model['capabilities'], ['术语核对'])
        remaining = self.client.get('/models').json()
        self.assertEqual(len(remaining), 2)
        self.assertEqual(next(c for c in remaining if c['id'] == self.other_id)['name'], 'Other model')

    def test_edit_missing_model_returns_404_without_creating_record(self):
        response = self.client.put('/models/999999', json={'name': 'Missing', 'provider': 'custom', 'model_id': 'none'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.client.get('/models').json()), 2)


class ProviderIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_providers_reach_translation_review_and_connection_check(self):
        from unittest.mock import patch, AsyncMock
        import httpx
        from app.core.config import settings
        from app.core.providers import PROVIDERS
        from app.api.other import test_provider_connection
        from app.schemas.schemas import TestProviderRequest
        from app.services.translation_service import TranslationService
        from app.services.mqm_review import MQMReviewService
        for provider in ('qwen', 'mimo', 'moonshot', 'zhipu', 'doubao', 'minimax', 'google'):
            with self.subTest(provider=provider), patch.object(settings, f'{provider}_api_key', 'test-key'):
                response = httpx.Response(200, json={'choices': [{'message': {'content': '[]'}}]}, request=httpx.Request('POST', 'https://example.org'))
                client = AsyncMock()
                client.post.return_value = response
                client.__aenter__.return_value = client
                with patch('httpx.AsyncClient', return_value=client):
                    model = PROVIDERS[provider]['model'] or 'account-specific-model'
                    self.assertEqual(await TranslationService().get_provider(provider).translate('test', model), '[]')
                    reviewed = await MQMReviewService().review_segment('原文', 'Translation', 'S001', provider, model)
                    self.assertTrue(reviewed['success'], reviewed)
                    checked = await test_provider_connection(TestProviderRequest(provider=provider, model=model))
                    self.assertTrue(checked['success'], checked)
                self.assertEqual(client.post.call_count, 3)
                for call in client.post.call_args_list:
                    self.assertEqual(call.args[0], PROVIDERS[provider]['base'] + '/chat/completions')
                    self.assertEqual(call.kwargs['json']['model'], model)
                    headers = call.kwargs['headers']
                    if provider == 'mimo':
                        self.assertEqual(headers['api-key'], 'test-key')
                        self.assertNotIn('Authorization', headers)
                    else:
                        self.assertEqual(headers['Authorization'], 'Bearer test-key')

    def test_partial_save_preserves_other_providers_and_escapes_values(self):
        import tempfile, os
        from pathlib import Path
        from unittest.mock import patch
        from dotenv import dotenv_values
        from app.api.other import save_api_keys
        from app.schemas.schemas import APIKeysSchema
        from app.core.config import settings
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, 'qwen_api_key', ''), patch.object(settings, 'mimo_api_key', 'unchanged'):
            try:
                os.chdir(directory)
                Path('.env').write_text('MIMO_API_KEY="unchanged"\nUNRELATED=retained\n')
                key = 'test-"quoted"-key\\suffix'
                save_api_keys(APIKeysSchema(qwen_api_key=key))
                data = dotenv_values('.env')
                self.assertEqual(data['QWEN_API_KEY'], key)
                self.assertEqual(data['MIMO_API_KEY'], 'unchanged')
                self.assertEqual(data['UNRELATED'], 'retained')
                self.assertEqual(settings.mimo_api_key, 'unchanged')
                self.assertEqual(settings.qwen_api_key, key)
            finally:
                os.chdir(previous)

if __name__ == '__main__':
    unittest.main()

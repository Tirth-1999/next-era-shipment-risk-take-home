"""Optional FastAPI tests; core-only installations skip this module."""
import pytest
pytest.importorskip('fastapi')
pytest.importorskip('httpx')
from fastapi.testclient import TestClient
from personal.demo import api


def test_new_stream_is_reproducible_and_capacity_changes(tmp_path, monkeypatch):
    """Preserve the seed while proving a changed capacity affects retained state."""
    original = api.ROOT
    (tmp_path / 'outputs').mkdir()
    (tmp_path / 'outputs/final_model').symlink_to(original / 'outputs/final_model')
    (tmp_path / 'src').symlink_to(original / 'src')
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    with TestClient(api.app) as client:
        results = [client.post('/api/interview/stream', json={'seed':1927,'shipments':5,'max_shipments':cap}).json() for cap in (2,4)]
        assert all(all(result['checks'].values()) for result in results)
        assert [r['first_replay']['peak_shipments'] for r in results] == [2,4]
        assert results[0]['events'] == results[1]['events']
        assert results[0]['output_directory'] != results[1]['output_directory']
        assert client.post('/api/interview/stream',json={'shipments':100000}).status_code == 422
        assert client.post('/api/interview/stream',json={},headers={'origin':'https://example.com'}).status_code == 403
        assert client.get('/docs').status_code == 200

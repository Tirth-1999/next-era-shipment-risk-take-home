"""The optional UI must display the same inputs and predictions as the engine."""
import hashlib
import json
import pytest
from personal.demo.server import Demo, ROOT
from dispatch_risk.features import canonical, FEATURE_VERSION


@pytest.fixture
def demo():
    instance=Demo()
    yield instance
    instance.temporary.cleanup()


def test_duplicate_and_future_correction_preserve_prediction(demo):
    first=demo.view()
    duplicate=demo.act({'action':'step'})
    correction=demo.act({'action':'step'})
    assert first['prediction']==duplicate['prediction']==correction['prediction']
    assert duplicate['deliveries'][1]['status']=='Duplicate delivery'
    assert correction['deliveries'][2]['status']=='Not yet available'
    noon=demo.act({'action':'view','as_of':'2026-01-01T12:00:00Z'})
    assert noon['features']['latest_temperature_c']==5
    assert noon['features']['temperature_count']==0  # 9 AM is the open left boundary.
    assert noon['deliveries'][0]['status']=='Superseded revision'


def test_eviction_features_match_the_engine(demo):
    result=demo.act({'action':'step','count':4})
    assert result['stats']['shipments']==2 and result['stats']['evictions']==1
    assert result['features']['latest_temperature_c'] is None
    assert 'shipment_not_retained' in result['prediction']['reasons']
    expected=hashlib.sha256(canonical({'feature_version':FEATURE_VERSION,'features':result['features']})).hexdigest()
    assert result['prediction']['feature_digest']==expected
    assert result['deliveries'][0]['status']=='Not retained'


def test_snapshot_restores_playback_and_prediction(demo):
    saved=demo.act({'action':'save'})
    demo.act({'action':'step','count':6})
    restored=demo.act({'action':'restore'})
    assert saved['prediction']==restored['prediction']
    assert saved['position']==restored['position']
    assert saved['stats']==restored['stats']
    assert 'byte for byte' in restored['message']


def test_both_reload_examples_preserve_state(demo):
    first=demo.view()
    for action in ('reload_valid','reload_invalid'):
        result=demo.act({'action':action})
        assert result['prediction']==first['prediction']
        assert result['stats']==first['stats']


def test_full_dataset_and_outcomes_remain_separate(demo):
    result=demo.act({'action':'reset','scenario':'sample','capacity':32})
    assert result['total']>10000
    result=demo.act({'action':'step','count':1000,'follow_time':True})
    assert result['position']==1001 and result['stats']['shipments']<=32
    before=demo.view()['prediction']
    assert 'reports' in demo.outcomes()
    assert demo.view()['prediction']==before


def test_invalid_reset_and_restore_do_not_destroy_session(demo):
    before=demo.view()
    for request in ({'action':'reset','capacity':0}, {'action':'reset','scenario':'bad'}, {'action':'restore'}):
        with pytest.raises(ValueError):demo.act(request)
    after=demo.view()
    assert before['prediction']==after['prediction']
    assert before['stats']==after['stats']


def test_tabs_have_independent_playback(demo):
    from personal.demo.server import Sessions
    sessions=Sessions(demo)
    first=sessions.get('a'*36)
    second=sessions.get('b'*36)
    try:
        first.act({'action':'step','count':3})
        assert first.position==4
        assert second.position==1
        assert sessions.get('a'*36) is first
        with pytest.raises(ValueError):sessions.get('bad session')
    finally:
        for item in sessions.sessions.values():item.temporary.cleanup()

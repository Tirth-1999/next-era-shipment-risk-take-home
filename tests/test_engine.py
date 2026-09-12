from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
import pytest
from dispatch_risk import RiskEngine, TelemetryEvent, build_training_rows
from dispatch_risk.features import FEATURES, FEATURE_VERSION, canonical, extract_features, normalize_event
from dispatch_risk.model import write_model
from dispatch_risk.engine import MAX_RECORDS_PER_SHIPMENT

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(eid='a', sid='s', hour=0, revision=0, value=5., received=None):
    return TelemetryEvent(eid, revision, sid, T+timedelta(hours=hour),
                          T+timedelta(hours=hour if received is None else received),
                          'temperature_c', value, 'sensor', {})


def artifact(path, prior=.1):
    write_model(path, dict(schema_version=1, feature_version=FEATURE_VERSION,
                         feature_order=FEATURES, lookback_hours=3, kind='constant',
                         prior=prior, medians=[0.]*9, means=[0.]*9,
                         scales=[1.]*9, weights=[0.]*18, intercept=0.))
    return path


@pytest.fixture
def engine(tmp_path):
    return RiskEngine(artifact(tmp_path/'model'))


def test_late_correction_does_not_change_past(engine):
    engine.ingest(event())
    before = engine.score('s', T).to_wire()
    engine.ingest(event(revision=1, value=9, received=2))
    assert engine.score('s', T).to_wire() == before
    assert engine.score('s', T+timedelta(hours=2)).feature_digest != engine.score('s', T).feature_digest


def test_duplicate_and_conflict_are_transactional(engine, tmp_path):
    assert engine.ingest(event())
    engine.snapshot(tmp_path/'before')
    assert not engine.ingest(event())
    with pytest.raises(ValueError):
        engine.ingest(event(value=8))
    with pytest.raises(ValueError):
        engine.ingest(event(sid='another'))
    engine.snapshot(tmp_path/'after')
    assert (tmp_path/'before').read_bytes() == (tmp_path/'after').read_bytes()


def test_lower_revision_is_available_before_correction(engine):
    engine.ingest(event(revision=2, received=2, value=9))
    engine.ingest(event(revision=1, received=1, value=7))
    expected = extract_features([normalize_event(event(revision=1, received=1, value=7))], 's', T+timedelta(hours=1))
    import hashlib
    assert engine.score('s', T+timedelta(hours=1)).feature_digest == hashlib.sha256(canonical({'feature_version':FEATURE_VERSION,'features':expected})).hexdigest()


def test_bad_clock_and_missing(engine):
    engine.ingest(event(hour=5, received=0))
    p=engine.score('s', T)
    assert p.degraded and 'future_device_clock_excluded' in p.reasons
    assert 'no_usable_temperature' in p.reasons
    assert engine.score('unknown', T).probability == .1


def test_caller_mutation_cannot_change_state(engine):
    payload={'nested': {'x':1}}
    e=replace(event(), payload=payload)
    engine.ingest(e)
    before=engine.score('s',T).to_wire()
    payload['nested']['x']=2
    assert engine.score('s',T).to_wire()==before
    with pytest.raises(ValueError):
        engine.ingest(e)


def test_replay_snapshot_restore_and_continuation(tmp_path):
    model=artifact(tmp_path/'model')
    a,b=RiskEngine(model,2),RiskEngine(model,2)
    stream=[event(),event(),event('b',hour=2),event(revision=1,received=3),event('c','other'),event('d','third')]
    results=[]
    for engine in (a,b):
        results.append([engine.score(e.shipment_id,e.received_at).to_wire() for e in stream if engine.ingest(e)])
    assert results[0]==results[1]
    a.snapshot(tmp_path/'a');b.snapshot(tmp_path/'b')
    assert (tmp_path/'a').read_bytes()==(tmp_path/'b').read_bytes()
    restored=RiskEngine.restore(model,tmp_path/'a')
    restored.snapshot(tmp_path/'c')
    assert (tmp_path/'a').read_bytes()==(tmp_path/'c').read_bytes()
    for engine in (a,restored):
        engine.ingest(event('next','fourth'))
    assert a.stats()==restored.stats()
    assert a.score('fourth',T).to_wire()==restored.score('fourth',T).to_wire()
    code="from pathlib import Path; from dispatch_risk import RiskEngine; e=RiskEngine.restore(Path(__import__('sys').argv[1]),Path(__import__('sys').argv[2])); e.snapshot(Path(__import__('sys').argv[3]))"
    subprocess.run([sys.executable,'-c',code,str(model),str(tmp_path/'b'),str(tmp_path/'fresh')],check=True)
    assert (tmp_path/'b').read_bytes()==(tmp_path/'fresh').read_bytes()


def test_capacity_over_ten_thousand_events(tmp_path):
    engine=RiskEngine(artifact(tmp_path/'model'),32)
    for i in range(10050):
        engine.ingest(event(str(i), str(i%100), hour=i/60))
    stats=engine.stats()
    assert stats['shipments']==32
    assert stats['retained_records']==stats['event_id_index']==32
    assert stats['evictions']==10018
    assert 'retention_coverage_unverified' in engine.score('49',T).reasons


def test_hot_shipment_bound_and_discarded_duplicate(engine,tmp_path):
    first=event('0')
    for i in range(MAX_RECORDS_PER_SHIPMENT+20):
        engine.ingest(event(str(i),hour=i/60))
    assert engine.stats()['retained_records']==MAX_RECORDS_PER_SHIPMENT
    assert engine.stats()['event_id_index']==MAX_RECORDS_PER_SHIPMENT
    assert not engine.ingest(first)
    assert 'history_truncated' in engine.score('s',T+timedelta(hours=3)).reasons
    engine.snapshot(tmp_path/'s')


def test_revision_flood_removes_whole_identity(engine):
    for i in range(MAX_RECORDS_PER_SHIPMENT+1):
        engine.ingest(event(revision=i, received=i/60))
    assert engine.stats()['retained_records']==0
    assert engine.stats()['event_id_index']==0
    assert not engine.ingest(event())


def test_reload_atomic_with_concurrent_calls(tmp_path):
    one=artifact(tmp_path/'one',.1);two=artifact(tmp_path/'two',.8)
    engine=RiskEngine(one)
    versions={RiskEngine(one).stats()['model_version']:.1,RiskEngine(two).stats()['model_version']:.8}
    engine.ingest(event())
    def scores():
        for _ in range(100):
            p=engine.score('s',T)
            assert versions[p.model_version]==p.probability
    def reloads():
        for _ in range(20):
            assert engine.reload_model(two)
            assert not engine.reload_model(tmp_path/'missing')
            assert engine.reload_model(one)
    def ingest():
        for i in range(50):
            engine.ingest(event(str(i), hour=i/60))
    with ThreadPoolExecutor(4) as pool:
        futures=[pool.submit(f) for f in (scores,scores,reloads,ingest)]
        for f in futures: f.result()
    assert engine.stats()['retained_records']==51
    before=engine.score('s',T).to_wire()
    (two/'model.json').write_text('{}')
    assert not engine.reload_model(two)
    assert engine.score('s',T).to_wire()==before


def test_snapshot_corruption_and_wrong_model(engine,tmp_path):
    model=artifact(tmp_path/'m',.8)
    engine.snapshot(tmp_path/'s')
    with pytest.raises(ValueError):RiskEngine.restore(model,tmp_path/'s')
    body=json.loads((tmp_path/'s').read_text());body['state']['accepted']=999
    (tmp_path/'s').write_text(json.dumps(body))
    with pytest.raises(ValueError):RiskEngine.restore(model,tmp_path/'s')


def test_utc_and_input_validation(engine):
    assert engine.score('s', T.astimezone(timezone(timedelta(hours=5)))).to_wire()==engine.score('s',T).to_wire()
    with pytest.raises(ValueError):engine.score('s',T.replace(tzinfo=None))
    for e in (replace(event(),value=float('nan')),replace(event(),revision=-1),replace(event(),payload={'large':'x'*20000})):
        with pytest.raises(ValueError):engine.ingest(e)
    assert engine.stats()['shipments']==0


def test_label_boundary_availability_and_maturity():
    decisions=[('s',T),('end',T+timedelta(days=5))]
    def label(hour,available=24):
        return dict(incident_id='i',shipment_id='s',incident_at=(T+timedelta(hours=hour)).isoformat(),label_available_at=(T+timedelta(hours=available)).isoformat())
    assert build_training_rows([], [label(0)], decisions)[0].label==0
    assert build_training_rows([], [label(6)], decisions)[0].label==1
    assert build_training_rows([], [label(6.01)], decisions)[0].label==0
    assert build_training_rows([], [label(6,200)], decisions)[0].label==0
    assert len(build_training_rows([],[],decisions))==1
    assert build_training_rows([],[],[('s',T)])==[]


def test_offline_features_match_online(engine):
    stream=[event(),event('b',hour=1,value=8),event(revision=1,received=3,value=3)]
    t=T+timedelta(hours=1)
    rows=build_training_rows(stream,[],[('s',t),('end',T+timedelta(days=5))])
    for e in reversed(stream):engine.ingest(e)
    import hashlib
    assert engine.score('s',t).feature_digest==hashlib.sha256(canonical({'feature_version':FEATURE_VERSION,'features':dict(rows[0].features)})).hexdigest()
    assert rows[0].features['temperature_trend_c_per_hour']==3


def test_snapshot_while_ingesting_is_recoverable(tmp_path):
    model=artifact(tmp_path/'model');engine=RiskEngine(model,8)
    def ingest():
        for i in range(300):engine.ingest(event(str(i),str(i%12),hour=i/60))
    def snapshot():
        for i in range(15):
            path=tmp_path/f'snapshot-{i}'
            engine.snapshot(path)
            recovered=RiskEngine.restore(model,path)
            recovered.snapshot(tmp_path/f'copy-{i}')
            assert path.read_bytes()==(tmp_path/f'copy-{i}').read_bytes()
            assert recovered.stats()['shipments']<=8
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(ingest),pool.submit(snapshot)]
        for f in futures:f.result()

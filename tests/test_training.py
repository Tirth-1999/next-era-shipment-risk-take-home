from datetime import timedelta
from dataclasses import replace
import importlib.util
from pathlib import Path
import numpy as np
from dispatch_risk import RiskEngine, build_training_rows, train
from dispatch_risk.features import event_from_mapping, utc
from dispatch_risk.training import _label
from test_engine import T, artifact


def test_generated_training_artifact_and_reproducibility(tmp_path):
    spec=importlib.util.spec_from_file_location('generator',Path(__file__).parents[1]/'tools/generate_dataset.py')
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    events, labels, decisions=generator.generate(1811,160)
    rows=build_training_rows(map(event_from_mapping,events),labels,((d['shipment_id'],utc(d['decision_time'])) for d in decisions))
    report=train(rows,tmp_path/'a')
    repeat=train(list(reversed(rows)),tmp_path/'b')
    assert report==repeat
    assert (tmp_path/'a/model.json').read_bytes()==(tmp_path/'b/model.json').read_bytes()
    test_start=utc(report['split']['test_start'])
    altered=[replace(r,label=1-r.label,metadata={**r.metadata,'outcome_incidents':[]}) if utc(r.metadata['cohort_first_decision'])>=test_start else r for r in rows]
    train(altered,tmp_path/'changed_test_labels')
    assert (tmp_path/'a/model.json').read_bytes()==(tmp_path/'changed_test_labels/model.json').read_bytes()
    assert report['model_kind']=='logistic_regression'
    assert report['test']['rows']>0
    assert {'source','freshness','trend'}=={s['dimension'] for s in report['slices']}
    engine=RiskEngine(tmp_path/'a')
    for e in events:engine.ingest(event_from_mapping(e))
    for r in rows[:5]:
        p=engine.score(r.shipment_id,r.decision_time)
        assert np.isfinite(p.probability) and 0<=p.probability<=1


def test_fit_cutoff_cannot_use_later_report():
    labels=[dict(incident_id='i',shipment_id='s',incident_at=(T+timedelta(hours=3)).isoformat(),label_available_at=(T+timedelta(hours=80)).isoformat())]
    row=build_training_rows([],labels,[('s',T),('end',T+timedelta(hours=100))])[0]
    assert row.label==1
    assert _label(row,T+timedelta(hours=53)) is None
    assert _label(row,T+timedelta(hours=54))==0  # Explicit completeness assumption can be contradicted later.
    assert _label(row,T+timedelta(hours=80))==1


def test_single_class_and_insufficient_split_fallback(tmp_path):
    rows=build_training_rows([],[],[('s',T),('end',T+timedelta(days=5))])
    report=train(rows,tmp_path/'model')
    assert report['model_kind']=='constant'
    assert report['test']['rows']==0
    assert RiskEngine(tmp_path/'model').score('x',T).probability==0.

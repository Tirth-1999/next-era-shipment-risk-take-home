"""Point-in-time examples and chronological evaluation of the selected model family."""
from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import hashlib
import json
import math
from .contracts import TrainingRow
from .features import FEATURES, FEATURE_VERSION, LOOKBACK_HOURS, aware, canonical, extract_features, identifier, normalize_event, utc
from .model import atomic_write, write_model

HORIZON=timedelta(hours=6)
GRACE=timedelta(hours=48)


def build_training_rows(events, labels, decision_times):
    decisions=sorted({(identifier(s,"shipment_id"),aware(t)) for s,t in decision_times},key=lambda x:(x[1],x[0]))
    if not decisions:
        return []
    cutoff=max(t for _,t in decisions)
    first={}
    for s,t in decisions:
        first.setdefault(s,t)
    cohorts=sorted(first,key=lambda s:(first[s],s))
    val=first[cohorts[min(int(len(cohorts)*.6),len(cohorts)-1)]]
    test=first[cohorts[min(int(len(cohorts)*.8),len(cohorts)-1)]]
    histories=defaultdict(list)
    identities={}
    owners={}
    for event in events:
        e=normalize_event(event)
        key=(e["event_id"],e["revision"])
        if e["event_id"] in owners and owners[e["event_id"]]!=e["shipment_id"]:
            raise ValueError("Event ID cannot change shipment")
        owners[e["event_id"]]=e["shipment_id"]
        if key in identities:
            if identities[key]!=e:
                raise ValueError("Conflicting duplicate event")
            continue
        identities[key]=e
        histories[e["shipment_id"]].append(e)
    incidents=defaultdict(list)
    seen={}
    for raw in labels:
        row=dict(raw)
        incident_id=identifier(row["incident_id"],"incident_id")
        sid=identifier(row["shipment_id"],"shipment_id")
        at=aware(row["incident_at"]) if not isinstance(row["incident_at"],str) else utc(row["incident_at"])
        available=aware(row["label_available_at"]) if not isinstance(row["label_available_at"],str) else utc(row["label_available_at"])
        if available<at:
            raise ValueError("Incident report cannot precede incident")
        item={"incident_id":incident_id,"shipment_id":sid,"incident_at":at.isoformat(),"label_available_at":available.isoformat()}
        if incident_id in seen:
            if item!=seen[incident_id]:
                raise ValueError("Conflicting incident identity")
            continue
        seen[incident_id]=item
        if available<=cutoff:
            incidents[sid].append(item)
    rows=[]
    censored=sum(t+HORIZON+GRACE>cutoff for _,t in decisions)
    for s,t in decisions:
        if t+HORIZON+GRACE>cutoff:
            continue  # Wait until the full outcome window and reporting allowance have passed.
        relevant=sorted([i for i in incidents[s] if t<utc(i["incident_at"])<=t+HORIZON],key=lambda i:(i["incident_at"],i["incident_id"]))
        features=extract_features(histories[s],s,t)
        source_events=[e for e in histories[s] if utc(e["received_at"])<=t]
        source=max(source_events,key=lambda e:(e["received_at"],e["event_id"],e["revision"]))["source"] if source_events else "unknown"
        metadata={"feature_version":FEATURE_VERSION,"source":source,"horizon_end":(t+HORIZON).isoformat(),"eligible_at":(t+HORIZON+GRACE).isoformat(),"observation_cutoff":cutoff.isoformat(),"validation_start":val.isoformat(),"test_start":test.isoformat(),"cohort_first_decision":first[s].isoformat(),"outcome_incidents":relevant,"negative_policy":"assumed complete after 48h reporting allowance","censored_decisions":censored,"requested_decisions":len(decisions)}
        rows.append(TrainingRow(s,t,features,int(bool(relevant)),metadata))
    return rows


def _label(row,cutoff):
    if row.decision_time+HORIZON+GRACE>cutoff:
        return None
    incidents=row.metadata.get("outcome_incidents")
    if incidents is not None:
        return int(any(utc(i["label_available_at"])<=cutoff and row.decision_time<utc(i["incident_at"])<=row.decision_time+HORIZON for i in incidents))
    available=row.metadata.get("label_available_at")
    if available is not None and utc(available)>cutoff:
        return None
    # External TrainingRows: caller asserts label completeness, with default 48h maturity.
    return row.label


def train(rows, artifact_dir):
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.impute import SimpleImputer, MissingIndicator
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, confusion_matrix
    from threadpoolctl import threadpool_limits
    rows=sorted(rows,key=lambda r:(aware(r.decision_time),r.shipment_id))
    if not rows:
        raise ValueError("No mature training rows; provide a longer observed time span")
    if len({(r.shipment_id,r.decision_time) for r in rows})!=len(rows):
        raise ValueError("Duplicate training checkpoint")
    for row in rows:
        if type(row.label) is not int or row.label not in (0,1):
            raise ValueError("Labels must be binary integers")
        if row.metadata.get("feature_version",FEATURE_VERSION)!=FEATURE_VERSION:
            raise ValueError("Training feature version mismatch")
        for name in FEATURES:
            v=row.features.get(name)
            if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)):
                raise ValueError("Features must be finite numeric values or None")
    first={}
    for row in rows:
        first.setdefault(row.shipment_id,utc(row.metadata["cohort_first_decision"]) if "cohort_first_decision" in row.metadata else row.decision_time)
    ordered=sorted(first,key=lambda s:(first[s],s))
    def consistent(field,default):
        values={r.metadata[field] for r in rows if field in r.metadata}
        if len(values)>1:
            raise ValueError("Mixed dataset cutoffs")
        return utc(next(iter(values))) if values else default
    val=consistent("validation_start",first[ordered[min(int(len(ordered)*.6),len(ordered)-1)]])
    test=consistent("test_start",first[ordered[min(int(len(ordered)*.8),len(ordered)-1)]])
    observation=consistent("observation_cutoff",max(r.decision_time for r in rows)+HORIZON+GRACE)
    def subset(group,cutoff):
        selected=[]; ys=[]
        for r in rows:
            belongs=(first[r.shipment_id]<val if group=="train" else val<=first[r.shipment_id]<test if group=="validation" else first[r.shipment_id]<test if group=="development" else first[r.shipment_id]>=test)
            y=_label(r,cutoff)
            if belongs and y is not None:
                selected.append(r);ys.append(y)
        return selected,np.array(ys,dtype=int)
    tr,yt=subset("train",val);va,yv=subset("validation",test);dev,yd=subset("development",test);te,ye=subset("test",observation)
    def X(rs):
        return pd.DataFrame([{name:r.features.get(name) for name in FEATURES} for r in rs],columns=FEATURES,dtype=float)
    def fit(rs,ys):
        if len(np.unique(ys))<2:
            return None
        prep=ColumnTransformer([("values",Pipeline([("impute",SimpleImputer(strategy="median",keep_empty_features=True)),("scale",StandardScaler())]),FEATURES),("missing",MissingIndicator(features="all"),FEATURES)],sparse_threshold=0)
        model=Pipeline([("prepare",prep),("model",LogisticRegression(C=1,max_iter=2000,random_state=1729))])
        with threadpool_limits(limits=1):
            model.fit(X(rs),ys)
        return model
    def measure(ys,p):
        if not len(ys):
            return {"rows":0,"positives":0,"average_precision":None,"brier":None,"log_loss":None,"recall_at_0_2":None,"precision_at_0_2":None}
        tn,fp,fn,tp=confusion_matrix(ys,p>=.2,labels=[0,1]).ravel()
        return {"rows":len(ys),"positives":int(ys.sum()),"average_precision":min(1.,float(average_precision_score(ys,p))) if len(np.unique(ys))==2 else None,"brier":float(brier_score_loss(ys,p)),"log_loss":float(log_loss(ys,np.clip(p,1e-15,1-1e-15),labels=[0,1])),"recall_at_0_2":float(tp/(tp+fn)) if tp+fn else None,"precision_at_0_2":float(tp/(tp+fp)) if tp+fp else None,"true_positive":int(tp),"false_positive":int(fp),"false_negative":int(fn)}
    fitted=fit(tr,yt) if tr else None
    val_p=fitted.predict_proba(X(va))[:,1] if fitted is not None and va else np.full(len(va),float(yt.mean()) if len(yt) else 0.5)
    prior=float(yt.mean()) if len(yt) else 0.5
    validation={"logistic_or_fallback":measure(yv,val_p),"constant":measure(yv,np.full(len(va),prior))}
    report={"schema_version":1,"configuration":"Regularized logistic fixed from notebook validation; no test-based reselection","split":{"validation_start":val.isoformat(),"test_start":test.isoformat(),"observation_cutoff":observation.isoformat(),"rule":"chronological shipment cohorts 60/20/20; horizon+48h maturity"},"validation":validation,"limitations":["Synthetic data; 48h mature-record completeness is an assumption","Latest decision time is an assumed observation snapshot, not certified audit coverage","20% threshold is illustrative, not a launch decision"]}
    if not dev:
        # With too little history to split, save a constant and omit held-out metrics.
        dev=rows;yd=np.array([r.label for r in rows]);te=[];ye=np.array([],dtype=int)
        report["limitations"].append("Insufficient chronological development span: fit constant on supplied mature rows; no held-out estimate")
        final=None
    else:
        final=fit(dev,yd)
    prior=float(yd.mean())
    p=final.predict_proba(X(te))[:,1] if final is not None and te else np.full(len(te),prior)
    report["test"]=measure(ye,p);report["constant_test"]=measure(ye,np.full(len(te),prior));report["development_rows"]=len(dev)
    report["slices"]=[]
    for dimension in ("source","freshness","trend"):
        groups={}
        for idx,r in enumerate(te):
            value=r.metadata.get("source","unknown") if dimension=="source" else ("missing" if r.features.get("measurement_age_minutes") is None else "older_than_30_minutes" if r.features["measurement_age_minutes"]>30 else "within_30_minutes") if dimension=="freshness" else ("missing" if r.features.get("temperature_trend_c_per_hour") is None else "present")
            groups.setdefault(value,[]).append(idx)
        for value,index in sorted(groups.items()):
            report["slices"].append({"dimension":dimension,"value":value,**measure(ye[index],p[index])})
    body={"schema_version":1,"feature_version":FEATURE_VERSION,"feature_order":FEATURES,"lookback_hours":LOOKBACK_HOURS,"kind":"constant" if final is None else "logistic_regression","prior":prior,"medians":[0.]*9,"means":[0.]*9,"scales":[1.]*9,"weights":[0.]*18,"intercept":0.,"training_cutoff":(observation if not report["test"]["rows"] and "Insufficient chronological" in " ".join(report["limitations"]) else test).isoformat(),"grace_hours":48,"training_library_version":sklearn.__version__,"training_rows_digest":hashlib.sha256(canonical([{ "shipment_id":r.shipment_id,"decision_time":r.decision_time.isoformat(),"features":dict(r.features),"label":int(y)} for r,y in zip(dev,yd)])).hexdigest()}
    if final is not None:
        prep=final.named_steps["prepare"].named_transformers_["values"]
        body.update(medians=prep.named_steps["impute"].statistics_.tolist(),means=prep.named_steps["scale"].mean_.tolist(),scales=prep.named_steps["scale"].scale_.tolist(),weights=final.named_steps["model"].coef_[0].tolist(),intercept=float(final.named_steps["model"].intercept_[0]))
    model=write_model(artifact_dir,body)
    if final is not None:
        expected=final.predict_proba(X(dev))[:,1]
        actual=np.array([model.predict(r.features) for r in dev])
        if not np.allclose(expected,actual,atol=1e-12,rtol=1e-12):
            raise ValueError("Portable scoring differs from trained pipeline")
    report["model_version"]=model.version;report["model_kind"]=model.kind
    atomic_write(Path(artifact_dir)/"evaluation.json",canonical(report))
    return report

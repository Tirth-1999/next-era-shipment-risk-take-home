"""Data preparation and model comparisons used by notebooks 11 onward."""
from pathlib import Path
import json, math, hashlib
import numpy as np
import pandas as pd
from dispatch_risk.features import utc, known_revisions, first_features, window_features
ROOT = Path(__file__).resolve().parents[3]
FEATURES = ["latest_temperature_c", "measurement_age_minutes", "arrival_delay_minutes", "temperature_missing", "temperature_count", "temperature_mean_c", "temperature_max_c", "temperature_trend_c_per_hour", "temperature_span_hours"]
GRACE_HOURS = 48
LOOKBACK_HOURS = 3
HORIZON = pd.Timedelta(hours=6)

def save_json(path, value):
    """Save data as JSON with repeatable key order.

    Args:
        path: Output file. Its parent folders are created if needed.
        value: Data to write as JSON.

    Returns:
        None. Writes the file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")

def load_jsonl(path):
    """Read the nonblank lines of a JSONL file.

    Args:
        path: Input file path.

    Returns:
        A list containing one parsed record per nonblank line.
    """
    with Path(path).open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def prepare_inputs(data_dir=None):
    """Build the input table and assign shipments to groups ordered by time.

    Args:
        data_dir: Raw data folder. Defaults to the repository data folder.

    Returns:
        The feature table, incident reports, and settings describing the split.
        Each shipment belongs to one group. The latest checkpoint is the assumed
        end of observation; it does not prove that reporting is complete.
    """
    data_dir = Path(data_dir) if data_dir else ROOT / "data"
    events = load_jsonl(data_dir / "events.jsonl")
    reports = pd.DataFrame(load_jsonl(data_dir / "labels.jsonl"), columns=["shipment_id", "incident_at", "label_available_at", "incident_id", "severity"])
    for col in ["incident_at", "label_available_at"]:
        reports[col] = pd.to_datetime(reports[col], utc=True)
    decisions = pd.DataFrame(load_jsonl(data_dir / "decision_times.jsonl"))
    decisions["decision_time"] = pd.to_datetime(decisions["decision_time"], utc=True)
    if decisions.duplicated(["shipment_id", "decision_time"]).any():
        raise ValueError("Duplicate decision checkpoints need an explicit policy")
    cohorts = decisions.groupby("shipment_id")["decision_time"].min().reset_index().sort_values(["decision_time", "shipment_id"])
    if len(cohorts) < 10:
        raise ValueError("Too few shipments for the experimental three-period evaluation")
    n = len(cohorts)
    val_start = cohorts.iloc[int(n * .6)]["decision_time"]
    test_start = cohorts.iloc[int(n * .8)]["decision_time"]
    # Assume observation ends at the latest checkpoint. Report coverage is unconfirmed.
    observation_cutoff = decisions["decision_time"].max()
    assignment = {r.shipment_id: ("train" if r.decision_time < val_start else "validation" if r.decision_time < test_start else "test") for r in cohorts.itertuples()}
    by_ship = {}
    for e in events:
        by_ship.setdefault(e["shipment_id"], []).append(e)
    rows = []
    for d in decisions.sort_values(["decision_time", "shipment_id"]).itertuples():
        when = d.decision_time.to_pydatetime()
        history = by_ship.get(d.shipment_id, [])
        features = first_features(history, d.shipment_id, when)
        features.update(window_features(history, d.shipment_id, when, LOOKBACK_HOURS))
        selected = [e for e in known_revisions(history, when) if e["kind"] == "temperature_c" and utc(e["device_time"]) <= utc(e["received_at"])]
        source = max(selected, key=lambda e: (utc(e["device_time"]), utc(e["received_at"]), e["event_id"]))["source"] if selected else "unknown"
        rows.append({"shipment_id": d.shipment_id, "decision_time": d.decision_time, "cohort": assignment[d.shipment_id], "source": source, **features})
    table = pd.DataFrame(rows)
    manifest = {"validation_start": val_start.isoformat(), "test_start": test_start.isoformat(), "observation_cutoff": observation_cutoff.isoformat(), "grace_hours": GRACE_HOURS, "lookback_hours": LOOKBACK_HOURS, "cohort_rule": "60/20/20 by shipment first decision time; ties assigned by time", "completeness_assumption": "Reports complete for horizons ending >=48h before the specified label cutoff; not guaranteed by input", "source_sha256": {name: hashlib.sha256((data_dir/name).read_bytes()).hexdigest() for name in ["events.jsonl", "decision_times.jsonl", "labels.jsonl"]}}
    return table, reports, manifest

def mature_labels(table, reports, cutoff, grace_hours=GRACE_HOURS):
    """Assign answers to examples whose reporting wait has passed.

    Args:
        table: Prediction checkpoints and input values.
        reports: Incident records, including arrival times.
        cutoff: Latest time at which a report can be used.
        grace_hours: Extra reporting time after the six hour prediction window.

    Returns:
        A copy of eligible rows with label and label_cutoff columns. A matching
        incident gives 1. No matching report gives 0 under the completeness
        assumption. Rows still waiting for reports are left out.
    """
    cutoff = pd.Timestamp(cutoff)
    eligible = table.loc[table["decision_time"] + HORIZON + pd.Timedelta(hours=grace_hours) <= cutoff].copy()
    known = reports.loc[reports["label_available_at"] <= cutoff]
    grouped = {sid: grp for sid,grp in known.groupby("shipment_id")}
    ys = []
    for row in eligible.itertuples():
        group = grouped.get(row.shipment_id)
        positive = group is not None and bool(((group["incident_at"] > row.decision_time) & (group["incident_at"] <= row.decision_time + HORIZON)).any())
        ys.append(int(positive))
    eligible["label"] = pd.Series(ys, index=eligible.index, dtype="int64")
    eligible["label_cutoff"] = cutoff
    return eligible

def development_data(data_dir=None):
    """Prepare the earlier training and model comparison groups.

    Args:
        data_dir: Raw data folder, or None for the supplied dataset.

    Returns:
        Training rows, validation rows, the full input table, reports and split
        settings. Labels use the reporting cutoff for each group.

    Raises:
        ValueError: If there are too few shipments or either fitting/comparison
            group lacks both incident and no incident examples.
    """
    table, reports, manifest = prepare_inputs(data_dir)
    train = mature_labels(table.loc[table.cohort == "train"], reports, manifest["validation_start"])
    validation = mature_labels(table.loc[table.cohort == "validation"], reports, manifest["test_start"])
    if train.label.nunique() < 2 or validation.label.nunique() < 2:
        raise ValueError("Training/validation need both classes for this comparison; report insufficient data rather than change split using test labels")
    assert set(train.shipment_id).isdisjoint(validation.shipment_id)
    return train, validation, table, reports, manifest

def imputation_pipeline(scale=False):
    """Create the steps that fill missing values and optionally scale inputs.

    Args:
        scale: Whether to subtract training averages and divide by training scales.

    Returns:
        An unfitted sklearn transformer. It learns medians when fitted and adds
        one missing value flag for each input.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer, MissingIndicator
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import StandardScaler
    # Add a missing value flag for every input, including inputs complete in training.
    numeric = [("impute", SimpleImputer(strategy="median", keep_empty_features=True))]
    if scale:
        numeric.append(("scale", StandardScaler()))
    return ColumnTransformer([("values", Pipeline(numeric), FEATURES), ("missing", MissingIndicator(features="all"), FEATURES)], sparse_threshold=0)

MODEL_ORDER = ["constant", "logistic_regression", "shallow_tree", "random_forest", "gradient_boosting"]
def candidate_models():
    """Create the five models used in the notebook comparison.

    Returns:
        A dictionary of unfitted sklearn pipelines: constant, logistic regression,
        small decision tree, random forest and gradient boosting. Each includes
        the required preparation of inputs.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    estimators = {
        "constant": DummyClassifier(strategy="prior"),
        "logistic_regression": LogisticRegression(C=1.0, max_iter=2000, random_state=1729),
        "shallow_tree": DecisionTreeClassifier(max_depth=3, min_samples_leaf=20, random_state=1729),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=10, n_jobs=1, random_state=1729),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=7, learning_rate=0.05, min_samples_leaf=20, l2_regularization=1.0, early_stopping=False, random_state=1729),
    }
    return {name: Pipeline([("prepare", imputation_pipeline(scale=name=="logistic_regression")), ("model", estimator)]) for name,estimator in estimators.items()}

def metrics(y, probability, threshold=0.2):
    """Compare predicted probabilities with known answers.

    Args:
        y: Actual answers, each 0 or 1.
        probability: One predicted probability per answer.
        threshold: Probability at which we count an alert; defaults to 0.2.

    Returns:
        Counts, ranking and probability error scores, and alert results. Empty
        input gives empty metrics. Threshold result names retain the suffix 0_2,
        so use the default threshold when interpreting those names.

    Raises:
        ValueError: If probabilities have the wrong shape or invalid values.
    """
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, precision_score, recall_score, confusion_matrix
    y = np.asarray(y,dtype=int); probability = np.asarray(probability,dtype=float)
    if not len(y):
        return {"rows":0,"positives":0,"average_precision":None,"brier":None,"log_loss":None,"precision_at_0_2":None,"recall_at_0_2":None}
    if probability.shape != y.shape or not np.isfinite(probability).all() or not ((probability>=0)&(probability<=1)).all():
        raise ValueError("Invalid prediction vector")
    classes = probability >= threshold
    tn,fp,fn,tp = confusion_matrix(y, classes, labels=[0,1]).ravel()
    return {"rows":len(y),"positives":int(y.sum()),"average_precision":float(average_precision_score(y,probability)) if len(np.unique(y))==2 else None,
            "brier":float(brier_score_loss(y,probability)),"log_loss":float(log_loss(y,np.clip(probability,1e-15,1-1e-15),labels=[0,1])),
            "precision_at_0_2":float(precision_score(y,classes,zero_division=0)) if classes.any() else None,
            "recall_at_0_2":float(recall_score(y,classes,zero_division=0)) if y.sum() else None,
            "true_positive":int(tp),"false_positive":int(fp),"true_negative":int(tn),"false_negative":int(fn)}

def validation_run(data_dir=None):
    """Fit candidate models and compare them on the validation group.

    Args:
        data_dir: Raw data folder, or None for the supplied dataset.

    Returns:
        Comparison table, selection details, fitted models, training rows,
        validation rows, the full input table and incident reports. Selection
        follows the declared Brier and simplicity rule.
    """
    from threadpoolctl import threadpool_limits
    train, validation, table, reports, manifest = development_data(data_dir)
    rows=[]; fitted={}
    with threadpool_limits(limits=1):
        for name, pipeline in candidate_models().items():
            pipeline.fit(train[FEATURES],train.label)
            probabilities = pipeline.predict_proba(validation[FEATURES])[:,1]
            rows.append({"model":name,**metrics(validation.label,probabilities)})
            fitted[name]=pipeline
    comparison=pd.DataFrame(rows)
    base=comparison.loc[comparison.model=="constant"].iloc[0]
    eligible=comparison.loc[(comparison.model!="constant") & (comparison.average_precision > base.average_precision) & (comparison.brier < base.brier)]
    if eligible.empty:
        winner="constant"
    else:
        # Apply the declared rule: allow a small Brier difference to choose a simpler model.
        near=eligible.loc[eligible.brier <= eligible.brier.min()+0.002]
        winner=min(near.model,key=MODEL_ORDER.index)
    selection={"selected_model":winner,"rule":"Improve validation AP and Brier over constant; choose simplest within 0.002 Brier of best eligible; otherwise constant", "simplicity_order":MODEL_ORDER, "threshold":0.2,"threshold_role":"Fixed teaching comparison only; not a deployment choice", "split":manifest,"validation_results":rows}
    return comparison,selection,fitted,train,validation,table,reports

def test_run():
    """Fit the chosen family on earlier data and evaluate later shipments.

    Returns:
        Selection details, the final model, constant baseline, development rows,
        test rows, model probabilities and baseline probabilities.

    Raises:
        ValueError: If the final group lacks enough outcomes for the comparison.
    """
    from threadpoolctl import threadpool_limits
    comparison, selection, _, _, _, table, reports = validation_run()
    policy = selection["split"]
    dev = mature_labels(table.loc[table.cohort != "test"], reports, policy["test_start"])
    test = mature_labels(table.loc[table.cohort == "test"], reports, policy["observation_cutoff"])
    if test.empty or test.label.nunique() < 2:
        raise ValueError("Insufficient held-out outcomes; no honest test AP available")
    assert set(dev.shipment_id).isdisjoint(test.shipment_id)
    assert (dev.decision_time+HORIZON+pd.Timedelta(hours=48) <= pd.Timestamp(policy["test_start"])).all()
    candidates = candidate_models()
    chosen = candidates[selection["selected_model"]]
    baseline = candidates["constant"]
    with threadpool_limits(limits=1):
        chosen.fit(dev[FEATURES],dev.label)
        baseline.fit(dev[FEATURES],dev.label)
        p = chosen.predict_proba(test[FEATURES])[:,1]
        base_p = baseline.predict_proba(test[FEATURES])[:,1]
    return selection,chosen,baseline,dev,test,p,base_p

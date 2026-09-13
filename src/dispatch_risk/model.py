"""Validated portable JSON scoring artifact; no executable pickle at serving time."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import os
import tempfile
from .features import FEATURES, FEATURE_VERSION, LOOKBACK_HOURS, canonical

MAX_ARTIFACT_BYTES=1_000_000

def atomic_write(path: Path, data: bytes):
    """Write bytes to a file with replace-on-success semantics.

    Args:
        path: Destination path.
        data: Bytes to persist.

    Returns:
        ``None``. Parent directories are created when needed.

    Notes:
        A temporary file is fsynced and then moved into place. If anything goes
        wrong before the replace step, the previous destination file is left
        intact.
    """
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary=tempfile.mkstemp(prefix="."+path.name+"-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

@dataclass(frozen=True)
class Model:
    """Portable scoring model loaded from ``model.json``.

    Attributes:
        version: SHA-256 digest over the artifact body.
        kind: Either ``logistic_regression`` or ``constant``.
        prior: Fallback incident probability used by constant models and for
            completely unretained shipments.
        medians: Training medians used to impute missing numeric features.
        means: Training means used by standard scaling.
        scales: Training scales used by standard scaling.
        weights: Logistic coefficients for scaled feature values followed by
            missingness indicators.
        intercept: Logistic intercept.
    """

    version: str
    kind: str
    prior: float
    medians: tuple[float,...]
    means: tuple[float,...]
    scales: tuple[float,...]
    weights: tuple[float,...]
    intercept: float

    def predict(self, features):
        """Score one feature dictionary.

        Args:
            features: Mapping containing every name in ``FEATURES``. Missing
                numeric values should be represented as ``None``.

        Returns:
            Probability between 0 and 1.

        Raises:
            KeyError: If a required feature is absent.
            ValueError: If a provided feature value is not finite.
        """
        if self.kind=="constant":
            return self.prior
        values=[]
        missing=[]
        for i,name in enumerate(FEATURES):
            value=features[name]
            absent=value is None
            if not absent and not math.isfinite(float(value)):
                raise ValueError("Nonfinite feature")
            values.append(((self.medians[i] if absent else float(value))-self.means[i])/self.scales[i])
            missing.append(float(absent))
        score=self.intercept+sum(w*x for w,x in zip(self.weights,values+missing))
        if score>=0:
            return 1/(1+math.exp(-score))
        e=math.exp(score)
        return e/(1+e)


def load_model(directory):
    """Load and validate a portable model artifact.

    Args:
        directory: Directory containing ``model.json``.

    Returns:
        A validated ``Model`` instance ready for serving.

    Raises:
        OSError: If the artifact cannot be read.
        ValueError: If the file is too large, the checksum does not match, the
            feature schema is incompatible, or any numeric value is invalid.
        KeyError: If required artifact fields are missing.
    """
    path=Path(directory)/"model.json"
    with path.open("rb") as handle:
        raw=handle.read(MAX_ARTIFACT_BYTES+1)
    if len(raw)>MAX_ARTIFACT_BYTES:
        raise ValueError("Model file exceeds size budget")
    data=json.loads(raw)
    version=data.pop("model_version",None)
    if version!=hashlib.sha256(canonical(data)).hexdigest():
        raise ValueError("Model integrity/version mismatch")
    if data.get("schema_version")!=1 or data.get("feature_version")!=FEATURE_VERSION or data.get("feature_order")!=FEATURES or data.get("lookback_hours")!=LOOKBACK_HOURS:
        raise ValueError("Incompatible model feature schema")
    if data.get("kind") not in ("logistic_regression","constant"):
        raise ValueError("Unsupported model kind")
    def number(value):
        """Validate one finite numeric field from the artifact."""
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError("Invalid model number")
        return float(value)
    def vector(name,length):
        """Validate one fixed-length numeric vector from the artifact."""
        values=data[name]
        if not isinstance(values,list) or len(values)!=length:
            raise ValueError("Wrong model vector length")
        return tuple(number(v) for v in values)
    prior=number(data["prior"])
    if not 0<=prior<=1:
        raise ValueError("Invalid prior")
    model=Model(version,data["kind"],prior,vector("medians",9),vector("means",9),vector("scales",9),vector("weights",18),number(data["intercept"]))
    if any(s<=0 for s in model.scales):
        raise ValueError("Invalid feature scale")
    for probe in ({name:None for name in FEATURES},{name:0 for name in FEATURES}):
        p=model.predict(probe)
        if not math.isfinite(p) or not 0<=p<=1:
            raise ValueError("Model smoke prediction failed")
    return model


def write_model(directory, body):
    """Write a model body and return the validated artifact.

    Args:
        directory: Output directory for ``model.json``.
        body: JSON-compatible model body without ``model_version``.

    Returns:
        The loaded ``Model`` after the artifact is written and validated.
    """
    data=dict(body)
    data["model_version"]=hashlib.sha256(canonical(body)).hexdigest()
    atomic_write(Path(directory)/"model.json",canonical(data))
    return load_model(directory)

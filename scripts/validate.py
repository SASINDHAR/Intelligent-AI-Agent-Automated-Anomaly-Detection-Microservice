"""Reproduce synthetic evaluation, examples, schema and test evidence."""
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
from fastapi.testclient import TestClient

# Run as `python -m scripts.validate` from the project root.
from app.main import Detector, MEAN, STD, Settings, create_app

root = Path(__file__).resolve().parents[1]
result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, capture_output=True, text=True)
(root / "docs/test-results.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
if result.returncode:
    raise SystemExit(result.stdout + result.stderr)
summary = [s for s in result.stdout.splitlines() if "passed" in s][-1]
detector = Detector()
rng = np.random.default_rng(93)
healthy = rng.normal(MEAN, STD, (500,3))
faults = rng.normal([110,12,22], STD, (100,3))
config = Settings()
config.llm_mode, config.webhook = "offline", ""
app = create_app(config)
(root / "docs/openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
timings=[]
with TestClient(app) as client:
    abnormal = json.loads((root / "examples/anomaly.json").read_text())
    example = client.post("/v1/telemetry", json=abnormal)
    example.raise_for_status()
    (root / "docs/example-response.json").write_text(json.dumps(example.json(), indent=2), encoding="utf-8")
    for _ in range(30):
        start=time.perf_counter()
        response=client.post("/v1/telemetry",json=abnormal)
        response.raise_for_status()
        timings.append((time.perf_counter()-start)*1000)
validation={"python":platform.python_version(),"platform":platform.platform(),"pytest_summary":summary,
            "synthetic_evaluation":{"seed":93,"healthy_count":500,"fault_count":100,"healthy_false_alarm_rate":float(np.mean(detector.model.predict(healthy)==-1)),"fault_recall":float(np.mean(detector.model.predict(faults)==-1))},
            "offline_testclient_latency_ms":{"count":30,"p50":float(np.percentile(timings,50)),"p95":float(np.percentile(timings,95)),"scope":"in-process TestClient, offline anomaly requests; not network throughput"},
            "external_llm":"mocked, no credentialed live call","webhook":"mocked success/failure; local HTTP integration recorded separately","docker":"not executed: Docker unavailable","cloud_run":"not deployed"}
(root/"docs/validation.json").write_text(json.dumps(validation,indent=2),encoding="utf-8")
print(json.dumps(validation,indent=2))

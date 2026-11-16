"""Send a deterministic 12-observation stream; run with the server listening."""
import argparse
from datetime import datetime, timezone
import os
import time

import httpx
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8080")
args = parser.parse_args()
rng = np.random.default_rng(7)
with httpx.Client(timeout=20) as client:
    for i in range(12):
        values = rng.normal([65, 2, 10], [2, .1, .3]) if i < 8 else rng.normal([110, 12, 22], [2, .1, .3])
        payload = dict(asset_id="motor-01", timestamp=datetime.now(timezone.utc).isoformat(), **dict(zip(["temperature_c", "vibration_mm_s", "current_a"], values)))
        response = client.post(args.url + "/v1/telemetry", json=payload, headers={"X-API-Key": os.getenv("INGEST_API_KEY", "")})
        response.raise_for_status()
        result = response.json()
        print(i, "ANOMALY" if result["detection"]["is_anomaly"] else "normal", result["workflow_status"])
        time.sleep(.25)

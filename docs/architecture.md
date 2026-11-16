# API and agent specification

## Endpoints

| Method and path | Input | Output / errors |
|---|---|---|
| GET `/healthz` | none | 200: status, model_loaded, llm_mode; startup finishes only after training |
| POST `/v1/telemetry` | Telemetry JSON; optional configured X-API-Key | 200 Result; 401 invalid key; 422 validation failure |
| GET `/docs` | none | Interactive Swagger documentation |
| GET `/openapi.json` | none | Complete machine-readable schemas |

Telemetry requires `asset_id` (1-64 ASCII letters/digits/underscore/dot/hyphen),
timezone-aware `timestamp`, numeric `temperature_c` [-50,250], `vibration_mm_s`
[0,100], `current_a` [0,500]. Numeric strings, booleans, nonfinite numbers, extra
fields and missing values are invalid. Bounds are demo sensor ranges, not safety
limits. Timestamps can be historical/future; no ordering or freshness gate exists.
One request represents one observation, no batch API. Replay is allowed.

Result contains UUID `event_id`, validated original telemetry, `detection` with
boolean `is_anomaly`, signed `decision_margin`, `model_version`, and
`deviations_sigma` for each feature. Normal results contain null `diagnosis`.
Anomaly diagnosis contains `summary`, `probable_causes`, `recommended_action`,
`source` (offline/llm/fallback), nullable `fallback_reason`, and
`requires_human_review: true`. Workflow status is not_needed/disabled/delivered/failed.
See the generated schema for exact field constraints and examples for real outputs.

## Agent execution and error policy

1. Validate inputs and configured ingestion credential.
2. Score the observation using a frozen seeded healthy-reference model.
3. On anomaly only, construct JSON evidence with measurements, margin and deviations.
4. Offline: produce deterministic inspection guidance. Live: send the system
   prompt and evidence to `/chat/completions`, requesting JSON object output.
5. Validate all returned fields and restrict the action to inspect_cooling,
   inspect_bearings, inspect_load or review_sensor. Extra fields are rejected.
6. On timeout, HTTP error, malformed response or schema failure use deterministic
   fallback with a machine-readable exception category. Do not expose provider bodies.
7. POST the event to the configured workflow endpoint if enabled. External
   failures do not erase anomaly results. Every recommendation requires human review.

The model has no tools that actuate equipment. Notification is a deterministic
application tool executed once per anomaly. This is deliberately bounded agent
orchestration. The prompt requests evidence-based hypotheses, not private reasoning
traces. Structured syntax and an action allowlist do not guarantee factual accuracy;
human review is necessary. Telemetry has no free-text instruction field.

LLM budget is 10 seconds, webhook budget 3 seconds. HTTP redirects are not followed,
avoiding credential forwarding. Operator-configured destinations are trusted config;
clients cannot override them. Request body/rate limits belong at the deployment
gateway. No outbound request is made for healthy telemetry.

## Scope and scaling

The endpoint waits for bounded diagnostics and notification before responding.
It is suitable for a small demo, not hard real-time control. Concurrent requests
share a read-only model and HTTP pool. Cold starts train the model once per process.
For higher throughput return 202 after durable enqueueing, keep model scoring near
ingestion, and let workers run diagnostics and deliver retries with backoff and
dead-letter handling. Use stable caller event IDs and durable uniqueness constraints
to deduplicate replays. Add object-store model versioning and a real calibration set.

No causal diagnosis, long-term storage, drift monitoring, safety certification,
real industrial calibration or production deployment is asserted.

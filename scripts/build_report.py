"""Optional report regeneration: pip install reportlab pypdf."""
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleCustom", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=colors.HexColor("#143344"), spaceAfter=10))
styles.add(ParagraphStyle(name="Deck", fontSize=10, leading=14, textColor=colors.HexColor("#486170"), spaceAfter=15))
styles.add(ParagraphStyle(name="SectionCustom", fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=colors.HexColor("#087F8C"), spaceBefore=13, spaceAfter=6))
styles.add(ParagraphStyle(name="CopyCustom", fontSize=9.5, leading=14, spaceAfter=7))
styles.add(ParagraphStyle(name="SmallCustom", fontSize=8, leading=11, spaceAfter=5))
story = []
def p(text, style="CopyCustom"):
    story.append(Paragraph(text, styles[style]))

p("Intelligent anomaly detection<br/>&amp; diagnostic agent", "TitleCustom")
p("HOPn technical evaluation | Design rationale &amp; implementation<br/>Duggireddy Sasindhar Reddy | sasindhar9542@gmail.com", "Deck")
p("01 / End-to-end architecture", "SectionCustom")
flow = [[Paragraph(t, styles["SmallCustom"]) for t in ["<b>INGEST</b><br/>FastAPI + schema<br/>Optional API key", "<b>DETECT</b><br/>Isolation Forest<br/>Signed margin", "<b>DIAGNOSE</b><br/>LLM + validation<br/>Offline fallback", "<b>NOTIFY</b><br/>n8n / REST POST<br/>Human review"]]]
table = Table(flow, colWidths=[123]*4)
table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1),colors.HexColor("#EAF4F5")),("BOX",(0,0),(-1,-1),.5,colors.HexColor("#AFCED1")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
story.append(table)
p("Normal observations return immediately without external calls. Flagged observations carry sensor values and baseline deviations to a bounded diagnostic workflow. The response exposes the detection, diagnosis source and webhook delivery outcome.")
p("02 / Why this stack", "SectionCustom")
p("<b>FastAPI + Pydantic:</b> typed request/response contracts, automatic OpenAPI documentation and explicit input errors. POST /v1/telemetry accepts one timezone-aware motor observation; GET /healthz exposes startup readiness. Numeric values, asset IDs and sensor ranges are validated.")
p("<b>Isolation Forest:</b> a small CPU baseline that needs no labelled faults. A seeded training set contains 2,000 healthy samples with temperature 65 +/- 5 C, vibration 2 +/- 0.35 mm/s and current 10 +/- 1 A. A negative decision margin flags an anomaly. The 2% contamination setting is a calibration choice, not an accuracy claim.")
p("<b>Compatible LLM adapter:</b> asynchronous HTTP supports Gemini's OpenAI-compatible endpoint or another configured Chat Completions provider. JSON output is parsed into a strict schema. The system prompt requests evidence-grounded hypotheses and an allowed inspection action. This is single-step agent orchestration; arbitrary tool execution is not implemented.")
p("03 / Reliable boundaries", "SectionCustom")
p("A live request has a 10-second LLM budget, followed by up to 3 seconds for the webhook, plus inference and queueing. Gemini receives a strict JSON Schema; providers that reject that mode get one JSON-object compatibility retry, still checked locally against the same Pydantic allowlist. Timeout, HTTP failure or invalid model output yields labelled deterministic fallback guidance. The model never issues physical control commands.")
p("Webhook delivery is synchronous and attempted once. A failed notification is visible in the result; no durable delivery or replay deduplication is claimed. An event UUID is sent as an Idempotency-Key for receiver-side deduplication. Authentication secrets and provider response bodies are excluded from application logs.")
p("<b>Scientific limit:</b> this steady-state synthetic baseline does not model temporal trends or asset-specific operating regimes. Feature deviations are descriptive, not causal attribution. Root-cause suggestions require inspection and real-world calibration.", "SmallCustom")
story.append(PageBreak())
p("Verification &amp; contribution plan", "TitleCustom")
p("HOPn technical evaluation | Reliability, scaling and six-month roadmap", "Deck")
p("04 / Test evidence and deployment readiness", "SectionCustom")
validation_path = ROOT / "docs/validation.json"
validation = json.loads(validation_path.read_text()) if validation_path.exists() else {}
p(f"<b>Local verification:</b> {validation.get('pytest_summary', 'See docs/validation.json for the executed test result')}. The suite exercises healthy/anomalous and sensor-boundary inputs, schema errors, authentication, repeatability, successful mocked LLM and webhook calls, JSON Schema compatibility retry, provider timeout/rate limits, malformed output, disallowed actions and delivery failure.")
metrics = validation.get("synthetic_evaluation", {})
if metrics:
    p(f"<b>Independent synthetic holdout:</b> {metrics['healthy_count']} healthy records produced a {metrics['healthy_false_alarm_rate']:.1%} false-alarm rate; {metrics['fault_count']} obvious multi-sensor faults produced {metrics['fault_recall']:.1%} recall. Seed 93 differs from training seed 42. Easy synthetic faults do not establish field performance.")
p("<b>Deployment verification:</b> the exact boundary telemetry replay returned a real Gemini diagnosis (source=llm, no fallback) in 2.46 seconds. Gemini calls allow 40 seconds inside a Vercel function capped at 60 seconds; unsupported JSON Schema mode retries once in JSON mode and validates locally. GitHub Actions passed 35 tests, Docker build and container health check. REST webhook passed locally; disabled on hosted demo. Cloud Run was blocked by disabled billing. Live API: hopn-anomaly.vercel.app/docs.")
p("<b>Scale path:</b> reuse the HTTP pool and keep inference off the event loop. Measure cold-start time and request p95 before tuning concurrency. At larger volume, split scoring from diagnostics using a durable queue; add backoff, dead-letter processing, persistent event IDs and an outbox. Store versioned model artifacts instead of retraining on startup.")
p("05 / Proposed six-month contribution roadmap", "SectionCustom")
roadmap = [
    ("Month 1", "Validate the foundation", "Collect sensor definitions and operating regimes; establish a labelled evaluation set, baseline tests and API contracts."),
    ("Month 2", "Improve signal quality", "Add per-asset baselines, rolling-window features and drift monitoring; report precision/recall and false alarms by regime."),
    ("Month 3", "Connect ROS 2 telemetry", "Build a timestamped ROS 2 bridge with buffering, backpressure and replay tests; measure acquisition-to-alert latency."),
    ("Month 4", "Add vision evidence", "Pilot YOLO-based visual inspection on approved datasets; align detections with telemetry and evaluate added diagnostic value."),
    ("Month 5", "Expand workflow automation", "Build multi-step n8n maintenance review flows, ticketing, deduplication and audit trails; test provider and queue outages."),
    ("Month 6", "Pilot and hand over", "Deploy a monitored pilot with CI/CD, model versioning, rollback and access controls; deliver runbooks and measured outcomes."),
]
rows = [[Paragraph(a, styles["SmallCustom"]), Paragraph(f"<b>{b}</b><br/>{c}", styles["SmallCustom"])] for a,b,c in roadmap]
t = Table(rows, colWidths=[65,427])
t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#EFF5F7"), colors.white]),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
story.append(t)
p("Primary references: ai.google.dev/gemini-api/docs/openai; docs.cloud.google.com/run/docs/container-contract; scikit-learn.org (IsolationForest API). Full links and executable commands are in README.md.", "SmallCustom")

def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#CEDCE0"))
    canvas.line(50,42,545,42)
    canvas.setFont("Helvetica",8)
    canvas.setFillColor(colors.HexColor("#486170"))
    canvas.drawString(50,29,"HOPn | Duggireddy Sasindhar Reddy | Technical evaluation")
    canvas.drawRightString(545,29,f"{doc.page} / 2")

target = ROOT / "docs/technical-summary.pdf"
SimpleDocTemplate(str(target), pagesize=A4, rightMargin=50, leftMargin=50, topMargin=42, bottomMargin=54, title="HOPn Technical Summary and Internship Roadmap", author="Duggireddy Sasindhar Reddy").build(story,onFirstPage=footer,onLaterPages=footer)
assert len(PdfReader(target).pages) == 2, "Report must be exactly two pages"
print(target)

"""IncidentIQ website and diagnostic API."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path, PureWindowsPath

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents import build_workflow
from ontology_engine import Ontology, label
from project_evidence import MAX_PROJECT


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
SCENARIOS = json.loads((ROOT / "data/scenarios.json").read_text(encoding="utf-8"))
MAX_STATUS = 64 * 1024
# Leave space for the snapshot and multipart metadata under Vercel's 4.5 MB cap.
PROJECT_LIMIT = 4 * 1024 * 1024 if os.getenv("VERCEL") == "1" else MAX_PROJECT


@asynccontextmanager
async def lifespan(app):
    app.state.ontology = await run_in_threadpool(Ontology, ROOT / "IncidentIQ-Final.owl")
    app.state.workflow = build_workflow(app.state.ontology)
    yield


app = FastAPI(title="IncidentIQ", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "web/index.html")


@app.get("/api/config")
def config():
    ontology = app.state.ontology
    return {
        "ontology": ontology.source,
        "reasoner": ontology.reasoner,
        "classes": ontology.classes,
        "faults": len(ontology.faults),
        "services": [{"id": key, "label": label(key)} for key in ontology.services],
        "scenarios": SCENARIOS,
        "nvidia": bool(os.getenv("NVIDIA_API_KEY")),
        "project_limit_mb": PROJECT_LIMIT // (1024 * 1024),
    }


@app.get("/api/status-template")
def status_template():
    ontology = app.state.ontology
    return JSONResponse(
        {"services": dict.fromkeys(ontology.services, "unknown"), "tests": dict.fromkeys(ontology.tests, "unknown")},
        headers={"Content-Disposition": 'attachment; filename="system_status.json"'},
    )


def status_section(data, name, identifiers, options):
    values = data.get(name, {})
    if not isinstance(values, dict):
        raise HTTPException(422, f'"{name}" must be an object keyed by ontology ID.')
    for key, value in values.items():
        if key not in identifiers:
            raise HTTPException(422, f'Unknown {name} ID "{key}". Use the IDs in the status template.')
        if not isinstance(value, str) or value.lower().strip() not in options:
            raise HTTPException(422, f'Invalid value for "{key}". Use {", ".join(sorted(options))}.')
    return {key: value.lower().strip() for key, value in values.items()}


async def read_upload(file, suffix, limit):
    if file is None:
        return None, None
    filename = PureWindowsPath(file.filename or "").name
    if not filename.lower().endswith(suffix):
        raise HTTPException(422, f"Upload a {suffix} file.")
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"The {suffix} file exceeds the {limit // 1024:,} KB limit.")
    if not data:
        raise HTTPException(422, f"The {suffix} file is empty.")
    return data, filename


@app.post("/api/diagnose")
async def diagnose(
    report: str = Form(max_length=2000),
    scenario: str = Form(default="database"),
    use_nvidia: bool = Form(default=False),
    status: UploadFile | None = File(default=None),
    project: UploadFile | None = File(default=None),
):
    report = report.strip()
    if not report:
        raise HTTPException(422, "Enter a description of the incident.")
    if scenario not in SCENARIOS and scenario != "project":
        raise HTTPException(422, "Choose an available scenario or investigate your project.")
    if scenario != "project" and (status is not None or project is not None):
        raise HTTPException(422, "Select My project to attach evidence.")
    status_data, status_name = await read_upload(status, ".json", MAX_STATUS)
    project_bytes, project_name = await read_upload(project, ".zip", PROJECT_LIMIT)
    if scenario == "project":
        snapshot = {}
        if status_data is not None:
            try:
                snapshot = json.loads(status_data.decode("utf-8-sig"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise HTTPException(422, "The status snapshot must contain valid UTF-8 JSON.") from exc
            if not isinstance(snapshot, dict) or not snapshot.keys() & {"services", "tests"}:
                raise HTTPException(422, 'Include a "services" or "tests" object in the status snapshot.')
        source = f"Uploaded snapshot · {status_name}" if status_name else "No status snapshot"
    else:
        snapshot = SCENARIOS[scenario]
        source = f"Simulation · {snapshot['label']}"
    ontology = app.state.ontology
    statuses = status_section(
        snapshot, "services", ontology.services, {"online", "offline", "down", "unavailable", "degraded", "unknown"},
    )
    tests = status_section(snapshot, "tests", ontology.tests, {"pass", "fail", "unknown"})
    try:
        state = await run_in_threadpool(app.state.workflow.invoke, {
            "report": report, "statuses": statuses, "test_results": tests, "status_source": source,
            "project_bytes": project_bytes, "project_name": project_name, "use_nvidia": use_nvidia,
        })
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**state["result"], "trace": state["trace"]}

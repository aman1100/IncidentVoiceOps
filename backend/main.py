import re
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import settings
from .agora_service import start_session, stop_session

logger = logging.getLogger('incident_voiceops.decisions')
ROOT = Path(__file__).resolve().parent.parent

@asynccontextmanager
async def app_lifespan(_app):
    # Mounted ASGI sub-apps do not receive lifespan events; explicitly start MCP sessions.
    from .mcp_server import mcp
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Incident VoiceOps", version="3.1.0", lifespan=app_lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

INCIDENT_ID = "PAY-SAN-2048"
state = {
    "status": "INVESTIGATING", "decision": None, "decided_at": None,
    "comment": None, "call_active": False, "session_id": None, "audit": [], "steps": []
}

class StopRequest(BaseModel):
    session_id: str

class VoiceDecision(BaseModel):
    transcript: str = Field(min_length=5, max_length=1200)

def canonicalize_id(text: str) -> str:
    value = text.lower().replace("-", " ")
    value = re.sub(r"[.,!?;:]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    variants = (
        "pay san twenty forty eight", "pay san two thousand forty eight",
        "pay san two zero four eight", "pay san two oh four eight",
        "pay san 2048",
    )
    for variant in variants:
        value = value.replace(variant, "pay san 2048")
    return value

def validate_mitigation(transcript: str) -> bool:
    # Authorization phrase is deliberately strict: no punctuation or hyphen variants.
    return re.sub(r"\s+", " ", transcript).strip().casefold() == "i authorize mitigation for incident pay san 2048"

def parse_ignore(transcript: str):
    # Require explicit ignore command, exact incident identifier, and a spoken comment.
    match = re.match(
        r"^\s*ignore\s+incident\s+PAY[\s-]+SAN[\s-]+(?:2048|twenty\s+forty\s+eight|two\s+thousand\s+forty\s+eight|two\s+zero\s+four\s+eight|two\s+oh\s+four\s+eight)\s*[.,;:]?\s*(?:my\s+)?comment\s+is\s+(.+?)\s*$",
        transcript, flags=re.IGNORECASE
    )
    if not match:
        return None
    comment = match.group(1).strip(" .,!?:;")
    return comment if len(comment) >= 3 else None

@app.get("/")
async def home():
    return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/api/health")
async def health():
    return {"ok": True, "credentials_configured": settings.ready,
            "mcp_configured": bool(settings.mcp_public_url and settings.mcp_auth_token),
            "mcp_public_url_configured": bool(settings.mcp_public_url),
            "agora_app_id_present": bool(settings.agora_app_id),
            "murf_key_present": bool(settings.murf_api_key)}

@app.get("/api/incident")
async def incident():
    return {**state, "incident_id": INCIDENT_ID, "severity": "SEV-1",
            "service": "Outbound Payments", "delayed_payments": 1284,
            "provider_timeout_rate": "38%", "queue_age_p95": "17 min"}

@app.post("/api/call/start")
async def call_start():
    if state["call_active"]:
        raise HTTPException(409, "A voice session is already active.")
    result = await start_session()
    state["call_active"] = True
    state["session_id"] = result["session_id"]
    return result

@app.post("/api/call/stop")
async def call_stop(request: StopRequest):
    if state["session_id"] and request.session_id != state["session_id"]:
        raise HTTPException(404, "Unknown session.")
    await stop_session(request.session_id)
    state["call_active"] = False
    state["session_id"] = None
    return {"ok": True}

def mitigation_steps():
    return [
        {"title": "Validate approved secondary sanctions provider", "detail": "Simulated health check passed; sanctions screening remains mandatory."},
        {"title": "Switch outbound route", "detail": "Simulated route switch to the validated secondary provider; no live routing changed."},
        {"title": "Replay delayed payments", "detail": "Simulated idempotent replay of 1,284 delayed payments; no real payments were submitted."},
        {"title": "Verify processing health", "detail": "Simulated queue recovery and provider health verification completed."},
    ]

def execute_mitigation(authorization_phrase: str, source: str = "MCP"):
    normalized = canonicalize_id(authorization_phrase)
    logger.info("MCP/decision mitigation received source=%s raw=%r normalized=%r", source, authorization_phrase, normalized)
    if not validate_mitigation(authorization_phrase):
        logger.warning("mitigation rejected source=%s normalized=%r", source, normalized)
        raise ValueError("Authorization phrase must be exactly: I authorize mitigation for incident PAY SAN 2048")
    if state["decision"]:
        raise ValueError("A decision has already been recorded. Reset the demo before making another decision.")
    decided_at = datetime.now(timezone.utc).isoformat()
    steps = mitigation_steps()
    state.update({"status": "MITIGATED (SIMULATED)", "decision": "MITIGATE",
                  "decided_at": decided_at, "comment": None, "steps": steps})
    state["audit"].append({"decision": "MITIGATE", "source": source,
                           "authorization_phrase": authorization_phrase,
                           "at": decided_at, "incident_id": INCIDENT_ID})
    logger.info("mitigation completed source=%s incident_id=%s", source, INCIDENT_ID)
    return {"ok": True, "status": state["status"], "decision": "MITIGATE", "incident_id": INCIDENT_ID,
            "decided_at": decided_at, "steps": steps,
            "message": "Simulated mitigation completed. No production systems or real payments were changed."}

def execute_ignore(ignore_phrase: str, comment: str, source: str = "MCP"):
    expected = "ignore incident pay san 2048"
    normalized_phrase = re.sub(r"\s+", " ", ignore_phrase).strip().casefold()
    clean_comment = (comment or "").strip()
    logger.info("ignore decision received source=%s phrase=%r comment=%r", source, ignore_phrase, clean_comment)
    if normalized_phrase != expected or len(clean_comment) < 3:
        logger.warning("ignore decision rejected source=%s", source)
        raise ValueError("Provide the exact phrase 'Ignore incident PAY SAN 2048' and a comment of at least 3 characters.")
    if state["decision"]:
        raise ValueError("A decision has already been recorded. Reset the demo before making another decision.")
    decided_at = datetime.now(timezone.utc).isoformat()
    state.update({"status": "IGNORED", "decision": "IGNORE", "decided_at": decided_at,
                  "comment": clean_comment, "steps": []})
    state["audit"].append({"decision": "IGNORE", "source": source,
                           "ignore_phrase": ignore_phrase, "comment": clean_comment,
                           "at": decided_at, "incident_id": INCIDENT_ID})
    logger.info("ignore decision accepted source=%s incident_id=%s", source, INCIDENT_ID)
    return {"ok": True, "status": "IGNORED", "decision": "IGNORE", "incident_id": INCIDENT_ID,
            "decided_at": decided_at, "comment": clean_comment,
            "message": "Incident marked ignored in this demo. No production incident state was changed."}

@app.post("/api/incident/mitigate")
async def mitigate(request: VoiceDecision):
    try:
        return execute_mitigation(request.transcript, source="manual-api")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/incident/ignore")
async def ignore(request: VoiceDecision):
    comment = parse_ignore(request.transcript)
    if not comment:
        raise HTTPException(400, "Ignore command not recognized. Say: Ignore incident PAY SAN 2048. My comment is followed by your reason.")
    try:
        return execute_ignore("Ignore incident PAY SAN 2048", comment, source="manual-api")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/incident/reset")
async def reset():
    state.update({"status": "INVESTIGATING", "decision": None,
                  "decided_at": None, "comment": None, "steps": []})
    return {"status": state["status"]}

# Agora connects to this mounted Streamable HTTP MCP endpoint.
from .mcp_server import mcp, protect_mcp_app
from mcp.server.transport_security import TransportSecuritySettings
from urllib.parse import urlparse
_mcp_host = urlparse(settings.mcp_public_url).hostname
_mcp_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[_mcp_host, f"{_mcp_host}:*"] if _mcp_host else [],
    allowed_origins=[],
)
mcp.settings.streamable_http_path = "/"
mcp.settings.transport_security = _mcp_security

mcp_http_app = mcp.streamable_http_app()
app.mount("/mcp", protect_mcp_app(mcp_http_app, settings.mcp_auth_token))

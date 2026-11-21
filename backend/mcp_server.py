"""Streamable HTTP MCP tools exposed to the Agora Conversational AI agent."""
import hmac
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from .main import execute_mitigation, execute_ignore

mcp = FastMCP(
    "VoiceOps",
    instructions=(
        "Tools for the simulated PAY-SAN-2048 incident. These tools only update local demo state; "
        "they never interact with production payments, sanctions providers, or routing."
    ),
)

@mcp.tool()
async def authorize_mitigation(authorization_phrase: str) -> dict:
    """Authorize and run the simulated mitigation. Requires the exact spoken phrase: I authorize mitigation for incident PAY SAN 2048. Call only after the engineer explicitly says the full phrase."""
    try:
        return execute_mitigation(authorization_phrase, source="agora-mcp")
    except ValueError as exc:
        return {"ok": False, "status": "REJECTED", "error": str(exc), "incident_id": "PAY-SAN-2048"}

@mcp.tool()
async def ignore_incident(ignore_phrase: str, comment: str) -> dict:
    """Record an explicit decision to ignore the incident. Requires ignore_phrase exactly 'Ignore incident PAY SAN 2048' and the engineer's actual spoken reason in comment."""
    try:
        return execute_ignore(ignore_phrase, comment, source="agora-mcp")
    except ValueError as exc:
        return {"ok": False, "status": "REJECTED", "error": str(exc), "incident_id": "PAY-SAN-2048"}

class MCPBearerAuthMiddleware:
    """Small ASGI middleware that preserves MCP streaming responses."""
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if not self.token:
            response = JSONResponse({"error": "MCP authentication is not configured"}, status_code=503)
            await response(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(supplied, expected):
            response = JSONResponse({"error": "Unauthorized MCP request"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

def protect_mcp_app(asgi_app, token: str):
    # Wrap ASGI directly so streamed MCP responses are not buffered by BaseHTTPMiddleware.
    secured_app = MCPBearerAuthMiddleware(asgi_app, token)
    return secured_app

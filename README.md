# Incident VoiceOps — Agora + Murf

FastAPI prototype for a simulated SEV-1 outbound-payments incident. Agora Conversational AI uses a Streamable HTTP MCP server hosted by this FastAPI backend. The agent can call two server-validated decision tools, and the dashboard polls backend state to show the matching result screen.

## Safety and credentials

- This is a simulation only. No real payment, sanctions, routing, ledger, or production incident system is connected.
- Do not commit `.env` or expose API credentials. The ZIP intentionally excludes `.env`, virtual environments, caches, and OS metadata.
- If credentials were ever shared publicly or in an untrusted chat, revoke and regenerate them before use.

## Requirements

- Python 3.10+
- Agora App ID and App Certificate
- Agora REST Customer ID and Customer Secret
- Murf API key
- A public HTTPS tunnel/host for the MCP endpoint
- A secure random MCP bearer token

## Install and run

```bash
cd incident-voiceops-agora-murf
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add newly generated credentials to `.env`. Also set:

- `MCP_PUBLIC_URL`: the public HTTPS base URL that Agora can reach, without `/mcp/`. For local development, expose port 8000 through a secure HTTPS tunnel and use the tunnel's HTTPS URL.
- `MCP_AUTH_TOKEN`: a long random secret. The backend requires this bearer token on every MCP request and passes it to Agora in the MCP server headers.

Start the backend from the project root:

```bash
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. Keep the HTTPS tunnel running for the entire Agora voice session. Agora cloud cannot reach `localhost` or a private LAN address.

## Voice workflow (Agora MCP)

1. Start the FastAPI backend and expose it through a public HTTPS URL. Set `MCP_PUBLIC_URL` to that base URL and `MCP_AUTH_TOKEN` to a long random secret.
2. Start the voice session in the dashboard. The backend starts an ephemeral Agora agent with `pipeline.llm.mcp_servers` configured for `https://<public-host>/mcp/` and `advanced_features.enable_tools=true`.
3. Agora's Deepgram ASR and LLM listen to the engineer. No separate browser SpeechRecognition listener is used for decisions.
4. To authorize simulated mitigation, say exactly: `I authorize mitigation for incident PAY SAN 2048`. Samar should call `authorize_mitigation` with that exact phrase.
5. To ignore the incident, say: `Ignore incident PAY SAN 2048. My comment is [your reason]`. Samar should call `ignore_incident` with the exact command phrase and the reason it heard.
6. The MCP tool validates the arguments on the backend, updates the simulated incident state, and returns a result to Agora. The dashboard polls `/api/incident` and automatically opens the Mitigated or Ignored result screen after the backend state changes.
7. The text fallback calls the same backend validation functions directly. Reset clears the decision so the demo can be run again.

The mitigation authorization is strict: the authorization phrase must contain only the exact words and digits shown above (case-insensitive, whitespace-normalized). Hyphens, punctuation, extra words, and vague agreement are rejected. The ignore tool requires the exact `Ignore incident PAY SAN 2048` command plus a comment of at least three characters. Only one decision is accepted until reset.

## MCP tools

- `authorize_mitigation(authorization_phrase: str)`: validates the exact authorization phrase, simulates the four runbook steps, and returns `MITIGATED (SIMULATED)` with step details.
- `ignore_incident(ignore_phrase: str, comment: str)`: validates the exact ignore command and non-empty reason, then returns `IGNORED` with the recorded comment.

Both tools are hosted at `/mcp/` using Streamable HTTP and protected by the configured bearer token. The public hostname is allowlisted for MCP DNS-rebinding protection. The backend starts the MCP session manager as part of the FastAPI application lifespan.

## Components

- `frontend/index.html`: incident dashboard and dedicated result screens.
- `frontend/app.js`: Agora connection, backend decision polling, manual fallback, and screen transitions.
- `backend/main.py`: FastAPI routes, shared decision state, server-side validation, MCP mount, and audit events.
- `backend/mcp_server.py`: the two Streamable HTTP MCP tools and bearer authentication.
- `backend/agora_service.py`: Agora Conversational AI MCP configuration, Deepgram ASR, and Murf TTS settings.
- `backend/config.py`: reads local environment configuration.

## Voice and troubleshooting notes

Agora's Deepgram ASR/LLM pipeline now owns the voice decision path. The dashboard does not need a second microphone listener. Browser polling only observes the backend decision state; it does not interpret speech. Backend logs show MCP tool calls, their source, validation outcomes, and audit events. Agora's internal ASR transcript is not copied into this dashboard's debug panel.

If the agent acknowledges the phrase but the screen does not change, check the backend console for an `agora-mcp` tool invocation. Also verify that the HTTPS tunnel is reachable from the internet, `MCP_PUBLIC_URL` matches its hostname, `MCP_AUTH_TOKEN` matches, and the Agora session was started after the current `.env` values were loaded. Check that `tools/list` on the `/mcp/` endpoint advertises the exact tool names `authorize_mitigation` and `ignore_incident`. For example, from a terminal, use `curl -X POST "$MCP_PUBLIC_URL/mcp/" -H "Authorization: Bearer $MCP_AUTH_TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`.

## API routes

- `GET /api/health`
- `GET /api/incident`
- `POST /api/call/start`
- `POST /api/call/stop`
- `POST /api/incident/mitigate` — text/manual fallback; requires the exact explicit authorization phrase
- `POST /api/incident/ignore` — text/manual fallback; requires the incident ignore command plus a comment
- `POST /api/incident/reset`
- `POST /mcp/` — Streamable HTTP MCP endpoint (bearer-authenticated); exposes `authorize_mitigation` and `ignore_incident`

## Demo state

Incident status and audit events are held in process memory and reset when the server restarts. This is not a production audit store.


## Voice decision debugging

The dashboard's **Voice Debug Log** records backend status polling, decision-state transitions, manual fallback API requests, and screen navigation. The backend console logs MCP tool invocation, accepted/rejected outcomes, and the simulated audit entry. It intentionally does not claim to contain Agora's internal ASR transcript.

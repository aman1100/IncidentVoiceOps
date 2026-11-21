import base64, secrets, time
import httpx
from fastapi import HTTPException
from agora_token_builder import RtcTokenBuilder
from .config import settings

API_BASE = 'https://preview.ai.agora.io/conversational-ai/v1/projects'

INCIDENT_INSTRUCTIONS = '''You are Incident VoiceOps, a calm production-support assistant. Speak concise, clear English.
SIMULATED INCIDENT PAY-SAN-2048, SEV-1: Outbound payments are queued because a sanctions screening provider has intermittent timeouts. 1,284 payments are delayed. Provider timeout rate is 38%; queue age p95 is 17 minutes; internal payment ledger is healthy; no confirmed duplicate debit or funds loss. AgentOps diagnostic runbook isolated the provider timeout path.
Suggested mitigation: pause new outbound submissions to the affected provider route, validate the approved secondary sanctions screening provider, switch traffic only after health validation, then replay only idempotently. NEVER bypass sanctions screening.
You may explain diagnosis, evidence, impact, mitigation, and risks. This prototype has no production payment connectivity. The engineer can choose exactly one of two simulated decisions by speaking an explicit command. ONLY after hearing the complete exact authorization phrase 'I authorize mitigation for incident PAY SAN 2048', call the MCP tool authorize_mitigation with authorization_phrase set to that exact phrase. Do not call it for a vague yes, paraphrase, implied consent, or partial phrase. ONLY after hearing 'Ignore incident PAY SAN 2048' followed by a spoken reason, call ignore_incident with ignore_phrase exactly 'Ignore incident PAY SAN 2048' and comment containing the reason. Never invent a comment. Wait for the tool result before telling the engineer the decision succeeded. If the tool rejects the request, explain the validation error and ask them to repeat the exact command. The tools perform simulated state changes only. Never claim that real payments were released or production was changed.'''

def make_rtc_token(channel, uid):
    expiry = int(time.time()) + 3600
    return RtcTokenBuilder.buildTokenWithUid(
        settings.agora_app_id, settings.agora_app_certificate,
        channel, uid, 1, expiry)

def auth_header():
    raw = f'{settings.agora_customer_id}:{settings.agora_customer_secret}'.encode()
    return 'Basic ' + base64.b64encode(raw).decode()

async def start_session():
    if not settings.ready:
        missing = [name for name, value in [
            ('AGORA_APP_ID', settings.agora_app_id),
            ('AGORA_APP_CERTIFICATE', settings.agora_app_certificate),
            ('AGORA_CUSTOMER_ID', settings.agora_customer_id),
            ('AGORA_CUSTOMER_SECRET', settings.agora_customer_secret),
            ('MURF_API_KEY', settings.murf_api_key)] if not value]
        raise HTTPException(400, 'Missing .env values: ' + ', '.join(missing))
    if not settings.mcp_public_url or not settings.mcp_auth_token:
        raise HTTPException(400, 'Configure MCP_PUBLIC_URL (public HTTPS base URL) and MCP_AUTH_TOKEN in .env before starting the Agora voice agent.')
    if not settings.mcp_public_url.startswith('https://'):
        raise HTTPException(400, 'MCP_PUBLIC_URL must be a publicly reachable HTTPS URL. Use a secure tunnel for local development.')

    channel = 'incident-voiceops-' + secrets.token_hex(5)
    user_uid = secrets.randbelow(900_000_000) + 100_000_000
    agent_uid = secrets.randbelow(900_000_000) + 100_000_000
    user_token = make_rtc_token(channel, user_uid)
    agent_token = make_rtc_token(channel, agent_uid)
    greeting = ('Hello. This is Incident VoiceOps. We have a severity one outbound payments incident. '
                'Sanctions screening provider timeouts are delaying 1,284 payments. I can walk you through '
                'the evidence, impact, mitigation options, and risks. No production action will be taken by this prototype.')
    body = {
      'agent': {
        'instructions': INCIDENT_INSTRUCTIONS,
        'greeting': {'mode': 'text', 'on': 'first_join', 'text': greeting},
        'pipeline': {
          'mode': 'cascaded',
          'asr': {'credential': {'mode': 'managed'}, 'vendor': 'deepgram', 'model': 'nova-3', 'language': 'en-US'},
          'llm': {
    'credential': {'mode': 'managed'},
    'vendor': 'openai',
    'style': 'openai',
    'model': 'gpt-4.1-mini',
    'max_history': 32,
    'failure_message': 'I am having trouble processing that. Please ask me again.',
    'mcp_servers': [
        {
            'name': 'voiceops',
            'endpoint': settings.mcp_public_url + '/mcp/',
            'transport': 'streamable_http',
            'headers': {
                'Authorization': 'Bearer ' + settings.mcp_auth_token
            },
            'allowed_tools': [
                'authorize_mitigation',
                'ignore_incident'
            ],
            'timeout_ms': 20000
        }
    ]
},
          'tts': {'credential': {'mode': 'byok', 'fields': {'api_key': settings.murf_api_key}},
                  'vendor': 'murf', 'url': 'wss://global.api.murf.ai/v1/speech/stream-input',
                  'params': {'voiceId': settings.murf_voice_id, 'locale': settings.murf_locale,
                             'rate': 0, 'pitch': 0, 'model': settings.murf_model, 'sample_rate': 24000}}
        }
      },
      'transport': {'type': 'rtc', 'channel': channel, 'token': agent_token,
                    'uid': str(agent_uid), 'subscribe_uids': [str(user_uid)], 'audio_scenario': 'aiserver'},
      'lifecycle': {
    'max_duration_ms': 3600000,
    'graceful_stop': {
        'enabled': True,
        'timeout_ms': 10000
    }
},
      'data_policy': {'retention': 'none'}
    }
    url = f'{API_BASE}/{settings.agora_app_id}/sessions/ephemeral'
    headers = {'Authorization': auth_header(), 'Content-Type': 'application/json'}
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f'Could not reach Agora ({exc.__class__.__name__}).')
    if response.is_error:
        print("AGORA ERROR STATUS:", response.status_code)
        print("AGORA ERROR BODY:", response.text)
        print("AGORA REQUEST ID:", response.headers.get("Agora-Request-Id"))

        raise HTTPException(
            502,
            f'Agora session start failed ({response.status_code}): {response.text[:1200]}'
        )
    data = response.json()
    session_id = data.get('agent_session_id')
    if not session_id:
        raise HTTPException(502, f'Agora response missing agent_session_id: {data}')
    return {'app_id': settings.agora_app_id, 'channel': channel, 'uid': user_uid,
            'token': user_token, 'session_id': session_id, 'status': data.get('status', 'STARTING')}

async def stop_session(session_id):
    if not settings.ready:
        raise HTTPException(400, 'Configure all required .env values first.')
    url = f'{API_BASE}/{settings.agora_app_id}/sessions/{session_id}/stop'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers={'Authorization': auth_header()})
    if response.is_error:
        raise HTTPException(502, f'Agora stop failed ({response.status_code}): {response.text[:1000]}')

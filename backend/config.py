import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    agora_app_id = os.getenv('AGORA_APP_ID', '').strip()
    agora_app_certificate = os.getenv('AGORA_APP_CERTIFICATE', '').strip()
    agora_customer_id = os.getenv('AGORA_CUSTOMER_ID', '').strip()
    agora_customer_secret = os.getenv('AGORA_CUSTOMER_SECRET', '').strip()
    murf_api_key = os.getenv('MURF_API_KEY', '').strip()
    murf_voice_id = os.getenv('MURF_VOICE_ID', 'Matthew').strip()
    murf_locale = os.getenv('MURF_LOCALE', 'en-US').strip()
    murf_model = os.getenv('MURF_MODEL', 'FALCON').strip()
    mcp_public_url = os.getenv('MCP_PUBLIC_URL', '').strip().rstrip('/')
    mcp_auth_token = os.getenv('MCP_AUTH_TOKEN', '').strip()

    @property
    def ready(self):
        return all([self.agora_app_id, self.agora_app_certificate,
                    self.agora_customer_id, self.agora_customer_secret,
                    self.murf_api_key])

settings = Settings()

"""Constants for the Solakon Cloud prototype."""

from datetime import timedelta

DOMAIN = "solakon_cloud"
PLATFORMS = ["sensor", "binary_sensor", "number", "switch"]

CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"

API_BASE_URL = "https://api.app.solakon.de"
AUTH_BASE_URL = "https://db.app.solakon.de/auth/v1"

# Supabase's anonymous browser key is intentionally public and is shipped in the
# Solakon web application. It identifies the client; it is not an account secret.
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJhbnprdXNmb3BzZHNleXR0cXZtIiw"
    "icm9sZSI6ImFub24iLCJpYXQiOjE3MDE0MjI1NjIsImV4cCI6MjAxNjk5ODU2Mn0."
    "7DSCHpXmLq2BJMwPvTNyDUc8Y6NkS_ZbOrQhKLbT4MU"
)

APP_VERSION = "1.102.19"
UPDATE_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT = 30

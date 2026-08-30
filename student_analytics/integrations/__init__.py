"""External data-source connectors.

Every connector follows the same contract:

    client = XClient()          # reads credentials from env / config
    client.available            # False when not configured -> caller uses mock mode
    client.test_connection()    # -> (ok: bool, message: str)
    client.fetch_*()            # -> pandas DataFrame in this project's schema

Nothing here is required for the dashboard to work: the generated dataset is the
default source of truth. Connectors let you replace or top-up that data with
real Canvas LMS gradebooks and Google Forms responses.
"""
from .canvas_api import CanvasClient
from .google_forms import GoogleFormsClient

__all__ = ["CanvasClient", "GoogleFormsClient"]

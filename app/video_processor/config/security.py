"""Local-mode security: no API key required."""

import os


def get_rate_limit_config():
    return {
        "max_requests_per_minute": 1000,
        "max_request_size_mb": 2000.0,
        # Disable API key validation for local Vyravid
        "enable_api_key_validation": os.getenv("ENABLE_PROCESSOR_AUTH", "false").lower() == "true",
    }

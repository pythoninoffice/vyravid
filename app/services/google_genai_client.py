"""Helpers for creating Google GenAI clients with an explicit backend."""

import os

from google import genai
from google.genai import types


def create_google_genai_api_client(api_key: str) -> genai.Client:
    """Create a Gemini client pinned to the developer API backend."""
    prev_use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
    try:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )
    finally:
        if prev_use_vertex is None:
            os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        else:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = prev_use_vertex

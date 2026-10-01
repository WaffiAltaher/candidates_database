"""
LLM client wrapper using AISuite for provider-agnostic API calls.
"""

import base64
import json
import logging

import aisuite as ai

logger = logging.getLogger(__name__)

# Singleton client — avoids re-creating on every call
_ai_client = None


def _get_client():
    global _ai_client
    if _ai_client is None:
        _ai_client = ai.Client()
    return _ai_client


class LLMClient:
    def __init__(self, model: str = "anthropic:claude-sonnet-4-20250514"):
        self.model = model

    def send_message(self, system_prompt: str, user_message: str) -> str:
        """Send a message to the LLM and return the text response."""
        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    def extract_json(self, system_prompt: str, user_message: str) -> dict:
        """Send a message expecting a JSON response. Parses and returns dict."""
        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\nRespond with valid JSON only. No markdown, no backticks, no explanation."},
                {"role": "user", "content": user_message},
            ],
        )
        return self._parse_json_response(response)

    def extract_json_from_pdf(self, system_prompt: str, pdf_path: str) -> dict:
        """Send a PDF file directly to the LLM for JSON extraction."""
        with open(pdf_path, "rb") as f:
            pdf_base64 = base64.standard_b64encode(f.read()).decode("utf-8")

        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\nRespond with valid JSON only. No markdown, no backticks, no explanation."},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the structured information from this CV.",
                        },
                    ],
                },
            ],
        )
        return self._parse_json_response(response)

    def _parse_json_response(self, response) -> dict:
        """Parse a JSON response from the LLM, with fallback for markdown-wrapped JSON."""
        text = response.choices[0].message.content
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON, attempting to extract JSON from response")
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
            raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

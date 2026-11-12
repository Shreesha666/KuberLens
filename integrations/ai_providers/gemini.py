"""
Google Gemini AI Provider Implementation.
Communicates with the Google Gemini API (gemini-2.0-flash) via standard HTTP REST,
requesting structured JSON adhering strictly to Master Specification Section 17.
Falls back seamlessly to StructuredRuleFallbackProvider on network or auth errors.
"""
import json
import logging
from datetime import UTC
from typing import Any

import requests

from integrations.ai_providers.base import AIAnalysisResultDTO, AIProviderBase
from integrations.ai_providers.fallback import StructuredRuleFallbackProvider

logger = logging.getLogger(__name__)


class GeminiAIProvider(AIProviderBase):
    """
    Google Gemini AI Provider utilizing the Gemini REST endpoint with structured JSON output.
    """
    provider_name: str = "gemini-2.0-flash"

    def __init__(self, api_key: str = "", model_name: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.fallback = StructuredRuleFallbackProvider()

    def generate_analysis(
        self,
        prompt: str,
        structured_context: dict[str, Any],
        role: str,
    ) -> AIAnalysisResultDTO:
        if not self.api_key:
            logger.info("No GEMINI_API_KEY set; using StructuredRuleFallbackProvider.")
            return self.fallback.generate_analysis(prompt, structured_context, role)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        system_instruction = (
            "You are an expert Indian stock market equity research AI. "
            "You MUST use ONLY the provided structured financial data and never hallucinate prices, ratios, or numbers. "
            "If any data points are missing or unverified, you MUST explicitly list them in 'missing_information'. "
            "Output MUST be a single valid JSON object strictly matching the schema with keys: "
            "overall_view (one of BUY_CANDIDATE, HOLD, WATCH, AVOID, REDUCE, EXIT), "
            "confidence_level (HIGH, MEDIUM, LOW), "
            "summary, positive_factors (list of strings), negative_factors (list of strings), "
            "technical_analysis (object), fundamental_analysis (object), risk_assessment (string), "
            "existing_holder_view (string), new_investor_view (string), entry_conditions (string), "
            "invalidation_conditions (string), missing_information (list of strings)."
        )

        user_content = f"Role: {role}\nInstructions: {prompt}\nStructured Stock Data:\n{json.dumps(structured_context, indent=2)}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\n{user_content}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = requests.post(
                endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini API returned zero candidates")

            text_content = candidates[0]["content"]["parts"][0]["text"]
            parsed = json.loads(text_content)

            symbol = structured_context.get("symbol", "")
            name = structured_context.get("company_name", symbol)
            quote = structured_context.get("quote", {})

            horizon_map = {
                "INVESTOR": "LONG_TERM",
                "SWING_TRADER": "SWING_TERM",
                "RISK_MANAGER": "PORTFOLIO_RISK",
            }

            return AIAnalysisResultDTO(
                stock_symbol=symbol,
                company_name=name,
                timestamp=datetime_now_iso(),
                data_freshness=quote.get("freshness", "CACHED"),
                analysis_horizon=horizon_map.get(role, "LONG_TERM"),
                overall_view=parsed.get("overall_view", "WATCH"),
                confidence_level=parsed.get("confidence_level", "MEDIUM"),
                summary=parsed.get("summary", ""),
                positive_factors=parsed.get("positive_factors", []),
                negative_factors=parsed.get("negative_factors", []),
                technical_analysis=parsed.get("technical_analysis", {}),
                fundamental_analysis=parsed.get("fundamental_analysis", {}),
                risk_assessment=parsed.get("risk_assessment", ""),
                existing_holder_view=parsed.get("existing_holder_view", ""),
                new_investor_view=parsed.get("new_investor_view", ""),
                entry_conditions=parsed.get("entry_conditions", ""),
                invalidation_conditions=parsed.get("invalidation_conditions", ""),
                missing_information=parsed.get("missing_information", structured_context.get("missing_information", [])),
                data_sources_and_assumptions=[
                    "National Stock Exchange (NSE) Official Data",
                    "Google Gemini Generative AI (Model: " + self.model_name + ")",
                    "Internal Fundamental and Technical Indicators Snapshot Engine",
                ],
                prompt_version="v1.0",
                model_name=self.model_name,
                raw_response=text_content,
            )

        except Exception as exc:
            logger.warning("Gemini API request failed (%s); falling back to StructuredRuleFallbackProvider.", exc)
            dto = self.fallback.generate_analysis(prompt, structured_context, role)
            dto.model_name = f"{self.model_name} (Fallback: {self.fallback.provider_name})"
            return dto


def datetime_now_iso() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()

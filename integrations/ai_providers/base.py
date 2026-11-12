"""
Abstract Base Class and Data Transfer Objects for AI Providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIAnalysisResultDTO:
    """
    Standardized AI output meeting all 16 items of Master Specification Section 17.
    """
    stock_symbol: str
    company_name: str
    timestamp: str
    data_freshness: str
    analysis_horizon: str
    overall_view: str
    confidence_level: str
    summary: str
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    technical_analysis: dict[str, Any] = field(default_factory=dict)
    fundamental_analysis: dict[str, Any] = field(default_factory=dict)
    risk_assessment: str = ""
    existing_holder_view: str = ""
    new_investor_view: str = ""
    entry_conditions: str = ""
    invalidation_conditions: str = ""
    missing_information: list[str] = field(default_factory=list)
    data_sources_and_assumptions: list[str] = field(default_factory=list)
    prompt_version: str = "v1.0"
    model_name: str = ""
    raw_response: str = ""


class AIProviderBase(ABC):
    """
    Abstract AI Provider Interface.
    Enforces that every provider accepts structured context data and returns a
    strictly typed AIAnalysisResultDTO without hallucinations.
    """
    provider_name: str = "base"

    @abstractmethod
    def generate_analysis(
        self,
        prompt: str,
        structured_context: dict[str, Any],
        role: str,
    ) -> AIAnalysisResultDTO:
        """
        Generate research analysis from structured context.

        :param prompt: Formatted prompt instructions.
        :param structured_context: Verified financial metrics dictionary.
        :param role: INVESTOR, SWING_TRADER, or RISK_MANAGER.
        :return: AIAnalysisResultDTO
        """
        pass


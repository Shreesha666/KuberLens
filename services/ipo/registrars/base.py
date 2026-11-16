"""
Base Registrar Adapter for Indian IPO Allotment Enquiry.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseRegistrarAdapter(ABC):
    """
    Abstract interface for registrar-specific allotment inquiry adapters.
    """
    registrar_key: str = "GENERIC"
    display_name: str = "Generic Registrar"
    portal_url: str = ""

    @abstractmethod
    def query_allotment(
        self,
        ipo_symbol: str,
        company_name: str,
        pan: str,
        application_number: str = "",
        demat_account: str = "",
    ) -> dict[str, Any]:
        """
        Queries registrar allotment status for a given PAN / Application.

        Returns:
            dict containing:
                success: bool
                status: 'ALLOTTED' | 'PARTIALLY_ALLOTTED' | 'NOT_ALLOTTED' | 'AWAITING' | 'NOT_FOUND' | 'ERROR'
                allotted_shares: int
                applied_shares: int
                refund_amount: Decimal
                message: str
                registrar_name: str
                raw_response: dict
        """
        raise NotImplementedError

"""
Indian Statutory Taxes & Brokerage Fee Calculator for Paper Trading.
Accurately models discount brokerage fees and statutory charges matching
the National Stock Exchange (NSE) & SEBI regulatory framework:
- Brokerage: Min(₹20, 0.03% of turnover)
- Securities Transaction Tax (STT): 0.1% for CNC (Delivery), 0.025% on sell for MIS (Intraday)
- Exchange Transaction Charges: 0.00297%
- Goods & Services Tax (GST): 18% on (Brokerage + Exchange Charges)
- SEBI Turnover Charges: 0.0001% (₹10 per crore)
- Stamp Duty: 0.015% for CNC Buy, 0.003% for MIS Buy
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class TaxBreakdown:
    turnover: Decimal
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    gst: Decimal
    sebi_charges: Decimal
    stamp_duty: Decimal
    total_charges: Decimal

    def as_dict(self) -> dict[str, Decimal]:
        return {
            "turnover": self.turnover,
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_charges": self.exchange_charges,
            "gst": self.gst,
            "sebi_charges": self.sebi_charges,
            "stamp_duty": self.stamp_duty,
            "total_charges": self.total_charges,
        }


class IndianTaxCalculator:
    """
    Computes precise statutory deductions and brokerage for simulated Indian equity trades.
    """
    BROKERAGE_MAX_CAP = Decimal("20.00")
    BROKERAGE_PERCENT = Decimal("0.0003")      # 0.03%
    EXCHANGE_TXN_RATE = Decimal("0.0000297")    # 0.00297% (NSE)
    GST_RATE = Decimal("0.18")                  # 18%
    SEBI_RATE = Decimal("0.000001")             # ₹10 per crore (0.0001%)
    STAMP_DUTY_CNC = Decimal("0.00015")         # 0.015% (Buy only)
    STAMP_DUTY_MIS = Decimal("0.00003")         # 0.003% (Buy only)
    STT_CNC = Decimal("0.001")                  # 0.1% (Both Buy & Sell)
    STT_MIS_SELL = Decimal("0.00025")           # 0.025% (Sell only)

    @classmethod
    def calculate(
        cls,
        quantity: int,
        price: Decimal,
        side: str,          # "BUY" or "SELL"
        product_type: str,  # "CNC" or "MIS"
    ) -> TaxBreakdown:
        qty = Decimal(str(quantity))
        turnover = (qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if turnover <= Decimal("0.00"):
            return TaxBreakdown(
                turnover=Decimal("0.00"),
                brokerage=Decimal("0.00"),
                stt=Decimal("0.00"),
                exchange_charges=Decimal("0.00"),
                gst=Decimal("0.00"),
                sebi_charges=Decimal("0.00"),
                stamp_duty=Decimal("0.00"),
                total_charges=Decimal("0.00"),
            )

        side_upper = side.upper()
        prod_upper = product_type.upper()

        # 1. Brokerage: flat ₹20 or 0.03% (whichever is lower)
        calculated_brokerage = turnover * cls.BROKERAGE_PERCENT
        brokerage = min(cls.BROKERAGE_MAX_CAP, calculated_brokerage).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 2. STT
        if prod_upper == "CNC":
            stt = (turnover * cls.STT_CNC).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif prod_upper == "MIS" and side_upper == "SELL":
            stt = (turnover * cls.STT_MIS_SELL).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            stt = Decimal("0.00")

        # 3. Exchange Transaction Charges
        exchange_charges = (turnover * cls.EXCHANGE_TXN_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 4. GST: 18% on (Brokerage + Exchange Charges)
        gst = ((brokerage + exchange_charges) * cls.GST_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 5. SEBI Turnover Charges
        sebi_charges = (turnover * cls.SEBI_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 6. Stamp Duty (Buy side only)
        if side_upper == "BUY":
            if prod_upper == "CNC":
                stamp_duty = (turnover * cls.STAMP_DUTY_CNC).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                stamp_duty = (turnover * cls.STAMP_DUTY_MIS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            stamp_duty = Decimal("0.00")

        total_charges = (brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return TaxBreakdown(
            turnover=turnover,
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            total_charges=total_charges,
        )

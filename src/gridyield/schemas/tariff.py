from pydantic import BaseModel, Field
from typing import List, Optional

class TimeOfUsePeriod(BaseModel):
    """Defines a Time-of-Use (TOU) pricing window and load constraint."""
    name: str = Field(..., description="e.g., Peak Shutdown, Daytime Partial, Night Full")
    rate_per_kwh: float = Field(..., description="Energy cost in $/kWh (or base currency)")
    start_hour: int = Field(..., ge=0, le=23, description="Start hour (0-23)")
    end_hour: int = Field(..., ge=0, le=23, description="End hour (0-23)")
    allowed_load_pct: float = Field(1.0, ge=0.0, le=1.0, description="Max allowed load fraction (e.g., 0.75 for 75%)")

class TariffStructure(BaseModel):
    """Complete tariff, tax, and voltage loss structure for a facility or grid contract."""
    contract_name: str
    base_rate_per_kwh: float = Field(..., description="Base rate $/kWh before taxes")
    tax_rate_pct: float = Field(0.0, ge=0.0, le=1.0, description="Applicable tax/VAT rate (e.g., 0.15 for 15% VAT)")
    tou_periods: List[TimeOfUsePeriod] = Field(default_factory=list)
    demand_charge_per_kw: float = Field(0.0, description="Monthly demand charge in $/kW of peak draw")
    high_to_low_voltage_loss_pct: float = Field(0.02, ge=0.0, le=0.15, description="Step-down transformer loss (HV to LV)")
    pue: float = Field(1.05, ge=1.0, le=2.0, description="Power Usage Effectiveness multiplier")
    seasonal_capacity_cap_pct: float = Field(1.0, ge=0.0, le=1.0, description="Grid-enforced capacity cap (e.g., 0.23 for 23% hydrology drop)")

    @property
    def effective_base_rate_per_kwh(self) -> float:
        """Returns base energy cost including VAT/tax."""
        return self.base_rate_per_kwh * (1.0 + self.tax_rate_pct)
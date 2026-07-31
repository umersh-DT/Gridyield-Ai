from pydantic import BaseModel, Field

class FleetSpecs(BaseModel):
    """Specifications for a mining fleet or compute hardware batch."""
    fleet_name: str = Field(..., description="e.g., Antminer S21, S19 Pro")
    total_hashrate_th: float = Field(..., gt=0, description="Total fleet hashrate in Terahashes (TH/s)")
    efficiency_j_per_th: float = Field(..., gt=0, description="Hardware efficiency in Joules/TH (or Watts per TH/s)")
    hosting_rate_charged_per_kwh: float = Field(0.065, description="Client hosting fee charged by operator in $/kWh")

class NetworkEconomics(BaseModel):
    """Network-level revenue parameters (e.g., Bitcoin network hashprice)."""
    hashprice_usd_per_th_day: float = Field(0.055, description="Bitcoin hashprice in $/TH/s/day")
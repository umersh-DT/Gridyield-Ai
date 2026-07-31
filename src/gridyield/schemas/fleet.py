from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class OwnershipType(str, Enum):
    CLIENT = "CLIENT"
    SELF_MINING = "SELF_MINING"

class HardwareBatch(BaseModel):
    """Represents a specific batch/model of mining hardware deployed at a facility."""
    batch_id: str = Field(..., description="Unique identifier for the batch (e.g., client_t21_batch_1)")
    model_name: str = Field(..., description="e.g., Antminer S21, T21, DG1+")
    ownership: OwnershipType = Field(OwnershipType.CLIENT, description="CLIENT or SELF_MINING")
    unit_count: int = Field(..., gt=0, description="Number of active physical units in this batch")
    hashrate_per_unit_th: float = Field(..., gt=0, description="Hashrate per unit in TH/s")
    power_per_unit_kw: float = Field(..., gt=0, description="Power draw per unit in kW")
    curtailment_priority: int = Field(
        default=1, 
        ge=1, 
        le=10, 
        description="Curtailment order priority (1 = Curtail First / Low Priority, 10 = Protect Last / High Priority)"
    )
    hosting_fee_rate_per_kwh: float = Field(0.065, description="Hosting rate billed to client in $/kWh (if CLIENT)")

    @property
    def total_batch_hashrate_th(self) -> float:
        """Returns total Hashes for the batch in TH/s."""
        return self.unit_count * self.hashrate_per_unit_th

    @property
    def total_batch_power_kw(self) -> float:
        """Returns total power draw for the batch in kW."""
        return self.unit_count * self.power_per_unit_kw

    @property
    def efficiency_j_per_th(self) -> float:
        """Calculates hardware efficiency in Joules per Terahash (J/TH or W/TH)."""
        if self.hashrate_per_unit_th == 0:
            return 0.0
        return (self.power_per_unit_kw * 1000.0) / self.hashrate_per_unit_th


class SiteFleetConfig(BaseModel):
    """Container schema for the entire facility's multi-batch hardware fleet."""
    site_id: str = Field(..., description="Identifier for the facility site")
    contracted_grid_capacity_kw: float = Field(..., gt=0, description="Contracted maximum power capacity in kW")
    batches: List[HardwareBatch] = Field(default_factory=list)

    @property
    def total_fleet_power_kw(self) -> float:
        """Returns aggregate power draw across all hardware batches in kW."""
        return sum(b.total_batch_power_kw for b in self.batches)

    @property
    def total_fleet_hashrate_th(self) -> float:
        """Returns aggregate hashrate across all hardware batches in TH/s."""
        return sum(b.total_batch_hashrate_th for b in self.batches)

    def get_batches_sorted_for_curtailment(self) -> List[HardwareBatch]:
        """
        Sorts batches by curtailment preference:
        1. Lowest priority first (curtailment_priority ascending).
        2. Lowest efficiency second (highest J/TH efficiency ratio).
        """
        return sorted(
            self.batches,
            key=lambda b: (b.curtailment_priority, -b.efficiency_j_per_th)
        )
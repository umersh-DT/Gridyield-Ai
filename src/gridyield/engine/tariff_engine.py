import numpy as np
import pandas as pd
from typing import Dict, Any
from gridyield.schemas.tariff import TariffStructure

class TariffEngine:
    """
    Vectorized calculation engine for energy tariffs, voltage transformer losses,
    tax/VAT structures, and time-of-use operational load caps.
    """
    def __init__(self, tariff: TariffStructure, facility_contract_kw: float = 10000.0):
        self.tariff = tariff
        self.facility_contract_kw = facility_contract_kw

    def process_power_series(self, df: pd.DataFrame, power_col: str = "kw_draw") -> pd.DataFrame:
        """
        Enriches a time-series power consumption DataFrame with HV gross power requirements,
        effective tax-adjusted rates, and window/seasonal load constraints.
        
        Expects a DataFrame indexed by DatetimeIndex.
        """
        result_df = df.copy()

        if not isinstance(result_df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be a DatetimeIndex for TOU and schedule processing.")

        # 1. HV/LV Transformer Loss and PUE adjustment
        pue_mult = self.tariff.pue
        hv_loss_mult = 1.0 + self.tariff.high_to_low_voltage_loss_pct

        # Convert net machine draw to gross HV grid draw
        result_df["gross_hv_kw"] = result_df[power_col] * pue_mult * hv_loss_mult

        # 2. Base rate initialization (including VAT)
        effective_base_rate = self.tariff.effective_base_rate_per_kwh
        rates = np.full(len(result_df), effective_base_rate, dtype=np.float64)
        
        # Load fraction multiplier (default 1.0 = 100% capacity)
        allowed_load_pcts = np.full(len(result_df), 1.0, dtype=np.float64)

        # 3. Apply Time-of-Use rate adjustments and window load limits
        hours = result_df.index.hour
        for period in self.tariff.tou_periods:
            if period.start_hour <= period.end_hour:
                mask = (hours >= period.start_hour) & (hours <= period.end_hour)
            else:
                # Overnight spans (e.g., 21:00 to 05:00)
                mask = (hours >= period.start_hour) | (hours <= period.end_hour)

            # Apply tax to TOU rate
            period_taxed_rate = period.rate_per_kwh * (1.0 + self.tariff.tax_rate_pct)
            rates[mask] = period_taxed_rate
            allowed_load_pcts[mask] = period.allowed_load_pct

        result_df["effective_rate_per_kwh"] = rates
        result_df["tou_allowed_load_pct"] = allowed_load_pcts

        # 4. Apply combined load capping (TOU limit vs. seasonal hydrology cap)
        result_df["seasonal_cap_pct"] = self.tariff.seasonal_capacity_cap_pct
        result_df["effective_capacity_limit_pct"] = np.minimum(
            result_df["tou_allowed_load_pct"],
            result_df["seasonal_cap_pct"]
        )

        result_df["max_allowable_kw"] = self.facility_contract_kw * result_df["effective_capacity_limit_pct"]

        # Cap actual draw at allowable capacity
        result_df["delivered_kw"] = np.minimum(result_df["gross_hv_kw"], result_df["max_allowable_kw"])

        # 5. Calculate interval energy cost (assuming hourly intervals)
        result_df["energy_cost"] = result_df["delivered_kw"] * result_df["effective_rate_per_kwh"]

        return result_df

    def compute_summary_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates aggregated summary metrics across the dataset."""
        total_net_kwh = df["kw_draw"].sum() if "kw_draw" in df.columns else 0.0
        total_delivered_hv_kwh = df["delivered_kw"].sum()
        total_energy_cost = df["energy_cost"].sum()
        peak_demand_kw = df["delivered_kw"].max()
        demand_charges = peak_demand_kw * self.tariff.demand_charge_per_kw

        total_facility_bill = total_energy_cost + demand_charges
        
        # Blended cost per actual kWh delivered to facility
        blended_effective_cost = total_facility_bill / total_delivered_hv_kwh if total_delivered_hv_kwh > 0 else 0.0

        return {
            "total_net_kwh": round(total_net_kwh, 2),
            "total_delivered_hv_kwh": round(total_delivered_hv_kwh, 2),
            "total_energy_cost_usd": round(total_energy_cost, 2),
            "peak_demand_kw": round(peak_demand_kw, 2),
            "demand_charge_usd": round(demand_charges, 2),
            "total_facility_bill_usd": round(total_facility_bill, 2),
            "blended_effective_cost_per_kwh": round(blended_effective_cost, 5)
        }
import numpy as np
import pandas as pd
from typing import Dict, Any
from gridyield.schemas.economics import FleetSpecs, NetworkEconomics

class ProfitabilityEngine:
    """
    Vectorized calculation engine for machine revenue, net hosting margin,
    and real-time profit-shield curtailment triggers.
    """
    def __init__(self, fleet: FleetSpecs, economics: NetworkEconomics):
        self.fleet = fleet
        self.economics = economics

    def calculate_fleet_profitability(self, tariff_processed_df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes the DataFrame output from TariffEngine and calculates instantaneous revenue,
        power expense, hosting margin, and curtailment actions.
        """
        df = tariff_processed_df.copy()

        # 1. Hardware Power Draw Check (KW = TH * (J/TH) / 1000)
        calculated_kw_draw = (self.fleet.total_hashrate_th * self.fleet.efficiency_j_per_th) / 1000.0

        # 2. Hourly Mining Revenue ($/hr) = (Hashrate_TH * Hashprice_TH_day) / 24
        hourly_revenue_per_th = self.economics.hashprice_usd_per_th_day / 24.0
        total_hourly_revenue = self.fleet.total_hashrate_th * hourly_revenue_per_th

        # Assign raw gross revenue to intervals where power is delivered
        # If site/window capacity caps delivered power, revenue scales proportionally
        df["power_availability_ratio"] = np.where(
            calculated_kw_draw > 0,
            df["delivered_kw"] / calculated_kw_draw,
            0.0
        )
        # Ratio cannot exceed 1.0
        df["power_availability_ratio"] = np.minimum(df["power_availability_ratio"], 1.0)

        df["gross_revenue_usd"] = total_hourly_revenue * df["power_availability_ratio"]

        # 3. Power Expense (from tariff engine)
        df["power_expense_usd"] = df["energy_cost"]

        # 4. Instantaneous Net Operational Margin ($/hr)
        df["net_margin_usd"] = df["gross_revenue_usd"] - df["power_expense_usd"]

        # 5. Breakeven Energy Cost Check ($/kWh threshold)
        # Power consumed in 1 hour (kWh) = delivered_kw
        df["breakeven_power_rate_per_kwh"] = np.where(
            df["delivered_kw"] > 0,
            df["gross_revenue_usd"] / df["delivered_kw"],
            0.0
        )

        # 6. Curtailment Decision Logic (Profit Shield)
        # Trigger CURTAIL if power cost per kWh exceeds mining revenue per kWh
        df["curtailment_action"] = np.where(
            df["effective_rate_per_kwh"] > df["breakeven_power_rate_per_kwh"],
            "CURTAIL_UNPROFITABLE",
            np.where(df["delivered_kw"] == 0, "CURTAIL_SCHEDULED", "RUN")
        )

        # Zero out margin if curtailed due to unprofitability
        df["protected_net_margin_usd"] = np.where(
            df["curtailment_action"] == "CURTAIL_UNPROFITABLE",
            0.0,
            df["net_margin_usd"]
        )

        return df

    def compute_financial_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Summarizes profitability and curtailment hours across the period."""
        total_revenue = df["gross_revenue_usd"].sum()
        total_power_cost = df["power_expense_usd"].sum()
        raw_net_margin = df["net_margin_usd"].sum()
        protected_margin = df["protected_net_margin_usd"].sum()

        total_hours = len(df)
        curtailed_unprofitable_hours = (df["curtailment_action"] == "CURTAIL_UNPROFITABLE").sum()
        curtailed_scheduled_hours = (df["curtailment_action"] == "CURTAIL_SCHEDULED").sum()
        running_hours = (df["curtailment_action"] == "RUN").sum()

        return {
            "total_gross_revenue_usd": round(total_revenue, 2),
            "total_power_cost_usd": round(total_power_cost, 2),
            "unprotected_net_margin_usd": round(raw_net_margin, 2),
            "protected_net_margin_usd": round(protected_margin, 2),
            "curtailment_savings_usd": round(protected_margin - raw_net_margin, 2),
            "running_hours": int(running_hours),
            "curtailed_scheduled_hours": int(curtailed_scheduled_hours),
            "curtailed_unprofitable_hours": int(curtailed_unprofitable_hours),
            "total_hours": int(total_hours)
        }
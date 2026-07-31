import numpy as np
import pandas as pd
from typing import Dict, Any
from gridyield.schemas.economics import FleetSpecs, NetworkEconomics
from gridyield.schemas.fleet import SiteFleetConfig, HardwareBatch

class ProfitabilityEngine:
    """
    Vectorized calculation engine for single-fleet machine revenue, net hosting margin,
    and real-time profit-shield curtailment triggers.
    """
    def __init__(self, fleet: FleetSpecs, economics: NetworkEconomics):
        self.fleet = fleet
        self.economics = economics

    def calculate_fleet_profitability(self, tariff_processed_df: pd.DataFrame) -> pd.DataFrame:
        df = tariff_processed_df.copy()

        # 1. Hardware Power Draw Check (KW = TH * (J/TH) / 1000)
        calculated_kw_draw = (self.fleet.total_hashrate_th * self.fleet.efficiency_j_per_th) / 1000.0

        # 2. Hourly Mining Revenue ($/hr) = (Hashrate_TH * Hashprice_TH_day) / 24
        hourly_revenue_per_th = self.economics.hashprice_usd_per_th_day / 24.0
        total_hourly_revenue = self.fleet.total_hashrate_th * hourly_revenue_per_th

        df["power_availability_ratio"] = np.where(
            calculated_kw_draw > 0,
            df["delivered_kw"] / calculated_kw_draw,
            0.0
        )
        df["power_availability_ratio"] = np.minimum(df["power_availability_ratio"], 1.0)
        df["gross_revenue_usd"] = total_hourly_revenue * df["power_availability_ratio"]

        # 3. Power Expense & Net Margin
        df["power_expense_usd"] = df["energy_cost"]
        df["net_margin_usd"] = df["gross_revenue_usd"] - df["power_expense_usd"]

        # 4. Breakeven Energy Cost Check ($/kWh)
        df["breakeven_power_rate_per_kwh"] = np.where(
            df["delivered_kw"] > 0,
            df["gross_revenue_usd"] / df["delivered_kw"],
            0.0
        )

        # 5. Curtailment Decision Logic
        df["curtailment_action"] = np.where(
            df["effective_rate_per_kwh"] > df["breakeven_power_rate_per_kwh"],
            "CURTAIL_UNPROFITABLE",
            np.where(df["delivered_kw"] == 0, "CURTAIL_SCHEDULED", "RUN")
        )

        df["protected_net_margin_usd"] = np.where(
            df["curtailment_action"] == "CURTAIL_UNPROFITABLE",
            0.0,
            df["net_margin_usd"]
        )

        return df

    def compute_financial_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
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


class MultiBatchProfitabilityEngine:
    """
    Vectorized calculation engine for multi-batch mining fleets.
    Supports priority-tier curtailment (e.g., curtails self-mining/low-priority batches 
    first during grid caps before touching client hardware).
    """
    def __init__(self, site_fleet: SiteFleetConfig, economics: NetworkEconomics):
        self.site_fleet = site_fleet
        self.economics = economics

    def calculate_site_profitability(self, tariff_processed_df: pd.DataFrame) -> pd.DataFrame:
        df = tariff_processed_df.copy()
        
        hourly_hashprice = self.economics.hashprice_usd_per_th_day / 24.0
        sorted_batches = self.site_fleet.get_batches_sorted_for_curtailment()

        # 1. Process base batch metrics
        for batch in sorted_batches:
            batch_kw = batch.total_batch_power_kw
            batch_th = batch.total_batch_hashrate_th
            batch_hourly_rev = batch_th * hourly_hashprice
            
            df[f"kw_{batch.batch_id}"] = batch_kw
            df[f"rev_{batch.batch_id}"] = batch_hourly_rev

        # 2. Allocate available power from highest priority to lowest priority
        remaining_site_kw = df["delivered_kw"].values.copy()

        for batch in reversed(sorted_batches):  # Protect highest priority (e.g., Priority 10) first
            batch_kw = batch.total_batch_power_kw
            
            allocated_kw = np.minimum(remaining_site_kw, batch_kw)
            df[f"delivered_kw_{batch.batch_id}"] = allocated_kw
            
            power_ratio = np.where(batch_kw > 0, allocated_kw / batch_kw, 0.0)
            df[f"delivered_rev_{batch.batch_id}"] = df[f"rev_{batch.batch_id}"] * power_ratio

            batch_breakeven = np.where(
                allocated_kw > 0,
                df[f"delivered_rev_{batch.batch_id}"] / allocated_kw,
                0.0
            )
            df[f"breakeven_{batch.batch_id}"] = batch_breakeven

            # Determine batch-level curtailment action
            # 1. Check zero allocation capacity cap first (CURTAIL_CAP)
            # 2. Check price breakeven threshold second (CURTAIL_UNPROFITABLE)
            # 3. Otherwise RUN
            df[f"action_{batch.batch_id}"] = np.where(
                allocated_kw == 0,
                "CURTAIL_CAP",
                np.where(
                    df["effective_rate_per_kwh"] > batch_breakeven,
                    "CURTAIL_UNPROFITABLE",
                    "RUN"
                )
            )

            remaining_site_kw -= allocated_kw

        # 3. Aggregate Site Financial Metrics
        df["site_gross_revenue_usd"] = sum(df[f"delivered_rev_{b.batch_id}"] for b in sorted_batches)
        df["site_power_expense_usd"] = df["energy_cost"]
        df["site_net_margin_usd"] = df["site_gross_revenue_usd"] - df["site_power_expense_usd"]

        return df
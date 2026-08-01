import argparse
import sys
import yaml
import pandas as pd
from pathlib import Path
from tabulate import tabulate

from gridyield.schemas.tariff import TariffStructure, TimeOfUsePeriod
from gridyield.schemas.economics import NetworkEconomics
from gridyield.schemas.fleet import SiteFleetConfig, HardwareBatch
from gridyield.engine.tariff_engine import TariffEngine
from gridyield.engine.profitability_engine import MultiBatchProfitabilityEngine


def load_config(config_path: Path) -> tuple[SiteFleetConfig, TariffStructure, NetworkEconomics]:
    """Parses a YAML site configuration into GridYield schema objects."""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    # 1. Parse Tariff
    tou_periods = [
        TimeOfUsePeriod(**tou) for tou in data.get("tariff", {}).get("tou_periods", [])
    ]
    tariff_data = data.get("tariff", {})
    tariff_data["tou_periods"] = tou_periods
    tariff = TariffStructure(**tariff_data)

    # 2. Parse Fleet Batches
    batches = [HardwareBatch(**b) for b in data.get("batches", [])]
    site_fleet = SiteFleetConfig(
        site_id=data["site_id"],
        contracted_grid_capacity_kw=data["contracted_grid_capacity_kw"],
        batches=batches
    )

    # 3. Parse Network Economics
    economics = NetworkEconomics(**data.get("network_economics", {}))

    return site_fleet, tariff, economics


def run_scenario(config_path: str, hours: int = 24, export_csv: str | None = None):
    """Executes a simulation scenario for a configured site."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    site_fleet, tariff, economics = load_config(path)

    # Create synthetic baseline power series assuming full facility load target
    target_power_kw = site_fleet.total_fleet_power_kw
    dates = pd.date_range("2026-08-01 00:00", periods=hours, freq="1h")
    input_df = pd.DataFrame({"kw_draw": [target_power_kw] * hours}, index=dates)

    # Run Tariff & Multi-Batch Profitability Engines
    tariff_engine = TariffEngine(tariff, facility_contract_kw=site_fleet.contracted_grid_capacity_kw)
    tariff_df = tariff_engine.process_power_series(input_df)

    profit_engine = MultiBatchProfitabilityEngine(site_fleet, economics)
    results_df = profit_engine.calculate_site_profitability(tariff_df)

    # Display Execution Summary Header
    print("\n" + "=" * 70)
    print(f"   GRIDYIELD AI SCENARIO RUNNER: {site_fleet.site_id.upper()}")
    print("=" * 70)
    print(f"Facility Name          : {site_fleet.site_id}")
    print(f"Contracted Capacity    : {site_fleet.contracted_grid_capacity_kw:,.1f} kW")
    print(f"Total Fleet Draw       : {site_fleet.total_fleet_power_kw:,.1f} kW")
    print(f"Total Fleet Hashrate   : {site_fleet.total_fleet_hashrate_th:,.1f} TH/s")
    print(f"Network Hashprice      : ${economics.hashprice_usd_per_th_day:.4f} / TH / day")
    print("-" * 70)

    # Fleet Batch Metrics Table
    batch_table = []
    for b in site_fleet.batches:
        batch_table.append([
            b.batch_id,
            b.model_name,
            b.ownership.value,
            b.unit_count,
            f"{b.total_batch_power_kw:,.1f} kW",
            f"{b.efficiency_j_per_th:.1f} J/TH",
            b.curtailment_priority
        ])

    print("\n--- DEPLOYED HARDWARE BATCHES ---")
    print(tabulate(
        batch_table, 
        headers=["Batch ID", "Model", "Owner", "Units", "Power Draw", "Efficiency", "Priority Tier"],
        tablefmt="github"
    ))

    # Overall Financial Summary
    total_rev = results_df["site_gross_revenue_usd"].sum()
    total_cost = results_df["site_power_expense_usd"].sum()
    net_margin = results_df["site_net_margin_usd"].sum()

    print("\n--- SIMULATION FINANCIAL RESULTS SUMMARY ---")
    summary_data = [
        ["Total Gross Revenue", f"${total_rev:,.2f}"],
        ["Total Grid Power Expense", f"${total_cost:,.2f}"],
        ["Net Operational Hosting Margin", f"${net_margin:,.2f}"],
        ["Average Hourly Margin", f"${net_margin / hours:,.2f} / hr"]
    ]
    print(tabulate(summary_data, headers=["Metric", "Value"], tablefmt="github"))

    # Export option
    if export_csv:
        out_path = Path(export_csv)
        results_df.to_csv(out_path)
        print(f"\n[+] Detailed hourly results exported cleanly to: {out_path.resolve()}")

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="GridYield AI - Site Scenario Runner CLI")
    parser.add_argument("--config", "-c", required=True, help="Path to site YAML configuration file")
    parser.add_argument("--hours", "-t", type=int, default=24, help="Simulation duration in hours (default: 24)")
    parser.add_argument("--export", "-e", help="Optional CSV file path to export hourly results")

    args = parser.parse_args()
    run_scenario(args.config, hours=args.hours, export_csv=args.export)


if __name__ == "__main__":
    main()
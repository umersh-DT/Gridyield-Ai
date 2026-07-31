import pandas as pd
from gridyield.schemas.tariff import TariffStructure, TimeOfUsePeriod
from gridyield.schemas.economics import FleetSpecs, NetworkEconomics
from gridyield.engine.tariff_engine import TariffEngine
from gridyield.engine.profitability_engine import ProfitabilityEngine

def test_profitability_and_curtailment_logic():
    # 1. Setup EEP Tariff ($0.0316 + 15% VAT = $0.03634/kWh base)
    # Spike peak rate to $0.20/kWh between 18:00 and 21:00 to test profit-shield curtailment
    tou_expensive = TimeOfUsePeriod(
        name="Expensive Peak",
        rate_per_kwh=0.20,
        start_hour=18,
        end_hour=21,
        allowed_load_pct=1.0
    )
    tariff = TariffStructure(
        contract_name="Test Contract",
        base_rate_per_kwh=0.0316,
        tax_rate_pct=0.15,
        tou_periods=[tou_expensive]
    )

    # 2. Setup Fleet (100,000 TH/s S21 Fleet at 17.5 J/TH -> ~1,750 kW draw)
    fleet = FleetSpecs(
        fleet_name="Antminer S21 Batch",
        total_hashrate_th=100000.0,
        efficiency_j_per_th=17.5
    )
    # Network hashprice: $0.055 per TH/s per day
    economics = NetworkEconomics(hashprice_usd_per_th_day=0.055)

    # 3. Run Tariff Engine
    dates = pd.date_range("2026-08-01 00:00", periods=24, freq="1h")
    df = pd.DataFrame({"kw_draw": [1750.0] * 24}, index=dates)
    tariff_engine = TariffEngine(tariff, facility_contract_kw=2000.0)
    processed_df = tariff_engine.process_power_series(df)

    # 4. Run Profitability Engine
    prof_engine = ProfitabilityEngine(fleet, economics)
    results_df = prof_engine.calculate_fleet_profitability(processed_df)
    summary = prof_engine.compute_financial_summary(results_df)

    # 5. Assertions
    # During normal hours ($0.03634/kWh), fleet should RUN profitably
    assert results_df.loc["2026-08-01 10:00", "curtailment_action"] == "RUN"
    
    # During expensive peak ($0.20 * 1.15 = $0.23/kWh), cost exceeds revenue -> CURTAIL_UNPROFITABLE
    assert results_df.loc["2026-08-01 19:00", "curtailment_action"] == "CURTAIL_UNPROFITABLE"

    # Protected margin must be >= unprotected margin because we avoided losing money during peak hours
    assert summary["protected_net_margin_usd"] >= summary["unprotected_net_margin_usd"]
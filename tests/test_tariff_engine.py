import pandas as pd
from gridyield.schemas.tariff import TariffStructure, TimeOfUsePeriod
from gridyield.engine.tariff_engine import TariffEngine

def test_eep_ethiopian_tariff_scenario():
    # 1. Setup EEP Tariff model ($0.0316 + 15% VAT, 2% HV loss, 1.05 PUE)
    tou_peak = TimeOfUsePeriod(
        name="Peak Shutdown",
        rate_per_kwh=0.0316,
        start_hour=18,
        end_hour=21,
        allowed_load_pct=0.0  # Full shutdown (0% load)
    )
    tou_daytime = TimeOfUsePeriod(
        name="Daytime Cap",
        rate_per_kwh=0.0316,
        start_hour=5,
        end_hour=17,
        allowed_load_pct=0.75  # 75% load cap
    )
    
    tariff = TariffStructure(
        contract_name="EEP Hydro-Grid Contract",
        base_rate_per_kwh=0.0316,
        tax_rate_pct=0.15,  # 15% VAT
        tou_periods=[tou_peak, tou_daytime],
        demand_charge_per_kw=0.0,
        high_to_low_voltage_loss_pct=0.02,  # 2% HV/LV loss
        pue=1.05,
        seasonal_capacity_cap_pct=1.0  # Full capacity available for base test
    )

    # 2. Create 24 hours of 10,000 kW (10 MW) steady draw data
    dates = pd.date_range("2026-08-01 00:00", periods=24, freq="1h")
    df = pd.DataFrame({"kw_draw": [10000.0] * 24}, index=dates)

    # 3. Process through TariffEngine
    engine = TariffEngine(tariff, facility_contract_kw=10000.0)
    processed_df = engine.process_power_series(df)
    summary = engine.compute_summary_metrics(processed_df)

    # 4. Peer Review Assertions
    # Tax-adjusted rate check ($0.0316 * 1.15 = ~$0.03634)
    expected_taxed_rate = round(0.0316 * 1.15, 5)
    assert round(processed_df.loc["2026-08-01 12:00", "effective_rate_per_kwh"], 5) == expected_taxed_rate

    # Check Peak Shutdown (19:00 -> 0 kW delivered)
    assert processed_df.loc["2026-08-01 19:00", "delivered_kw"] == 0.0

    # Check Daytime Cap (12:00 -> 75% cap of 10 MW = 7,500 kW)
    assert processed_df.loc["2026-08-01 12:00", "delivered_kw"] == 7500.0

    # Check Summary outputs exist
    assert summary["total_energy_cost_usd"] > 0
    assert summary["blended_effective_cost_per_kwh"] > 0.0316
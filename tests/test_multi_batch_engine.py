import pandas as pd
from gridyield.schemas.tariff import TariffStructure, TimeOfUsePeriod
from gridyield.schemas.economics import NetworkEconomics
from gridyield.schemas.fleet import SiteFleetConfig, HardwareBatch, OwnershipType
from gridyield.engine.tariff_engine import TariffEngine
from gridyield.engine.profitability_engine import MultiBatchProfitabilityEngine

def test_tiered_curtailment_allocates_power_to_client_first():
    # 1. Setup Tariff with a 50% daytime load cap
    tou_cap = TimeOfUsePeriod(
        name="Daytime Cap",
        rate_per_kwh=0.0316,
        start_hour=8,
        end_hour=16,
        allowed_load_pct=0.50  # 50% capacity restriction
    )
    tariff = TariffStructure(
        contract_name="EEP Hydro",
        base_rate_per_kwh=0.0316,
        tax_rate_pct=0.15,
        tou_periods=[tou_cap]
    )

    # 2. Setup Fleet: Priority 1 Self-Mining (1,000 kW) vs Priority 10 Client Mining (1,000 kW)
    batch_self = HardwareBatch(
        batch_id="self_mining_dg1",
        model_name="DG1+",
        ownership=OwnershipType.SELF_MINING,
        unit_count=300,
        hashrate_per_unit_th=11.0,
        power_per_unit_kw=3.33,  # ~1,000 kW total
        curtailment_priority=1   # Low Priority / Curtail First
    )

    batch_client = HardwareBatch(
        batch_id="client_s21",
        model_name="S21+",
        ownership=OwnershipType.CLIENT,
        unit_count=260,
        hashrate_per_unit_th=235.0,
        power_per_unit_kw=3.85,  # ~1,000 kW total
        curtailment_priority=10  # High Priority / Protect Last
    )

    fleet = SiteFleetConfig(
        site_id="site_alpha",
        contracted_grid_capacity_kw=2000.0,
        batches=[batch_self, batch_client]
    )

    # 3. Process 24 hours of data through Tariff and MultiBatch engines
    dates = pd.date_range("2026-08-01 00:00", periods=24, freq="1h")
    df = pd.DataFrame({"kw_draw": [2000.0] * 24}, index=dates)

    tariff_engine = TariffEngine(tariff, facility_contract_kw=2000.0)
    processed_df = tariff_engine.process_power_series(df)

    economics = NetworkEconomics(hashprice_usd_per_th_day=0.055)
    multi_engine = MultiBatchProfitabilityEngine(fleet, economics)
    results_df = multi_engine.calculate_site_profitability(processed_df)

    # 4. Assertions during 50% daytime cap hour (12:00 -> Delivered power limited to 1,000 kW)
    # High-priority client batch gets the full 1,000 kW delivered (RUN)
    assert results_df.loc["2026-08-01 12:00", "delivered_kw_client_s21"] > 990.0
    assert results_df.loc["2026-08-01 12:00", "action_client_s21"] == "RUN"

    # Low-priority self-mining batch gets 0 kW delivered (CURTAIL_CAP)
    assert results_df.loc["2026-08-01 12:00", "delivered_kw_self_mining_dg1"] == 0.0
    assert results_df.loc["2026-08-01 12:00", "action_self_mining_dg1"] == "CURTAIL_CAP"
    
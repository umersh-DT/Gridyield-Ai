from gridyield.schemas.fleet import SiteFleetConfig, HardwareBatch, OwnershipType

def test_multi_batch_fleet_curtailment_sorting():
    # Setup mixed hardware batches: Client T21s, Client S21+s, and Self-Mining DG1+s
    batch_t21 = HardwareBatch(
        batch_id="client_t21",
        model_name="Antminer T21",
        ownership=OwnershipType.CLIENT,
        unit_count=3447,
        hashrate_per_unit_th=190.0,
        power_per_unit_kw=3.61,  # ~19.0 J/TH
        curtailment_priority=5   # Mid priority
    )

    batch_s21_plus = HardwareBatch(
        batch_id="client_s21_plus",
        model_name="Antminer S21+",
        ownership=OwnershipType.CLIENT,
        unit_count=233,
        hashrate_per_unit_th=235.0,
        power_per_unit_kw=3.87,  # ~16.5 J/TH
        curtailment_priority=10  # Highest priority (Protect Last)
    )

    batch_dg1_self = HardwareBatch(
        batch_id="self_dg1_plus",
        model_name="DG1+",
        ownership=OwnershipType.SELF_MINING,
        unit_count=52,
        hashrate_per_unit_th=11.0,
        power_per_unit_kw=3.4,
        curtailment_priority=1   # Lowest priority (Curtail First)
    )

    fleet = SiteFleetConfig(
        site_id="ethiopia_substation_alpha",
        contracted_grid_capacity_kw=15000.0,
        batches=[batch_t21, batch_s21_plus, batch_dg1_self]
    )

    # Assert totals
    assert fleet.total_fleet_power_kw > 10000.0
    assert fleet.total_fleet_hashrate_th > 500000.0

    # Assert curtailment sorting order
    sorted_batches = fleet.get_batches_sorted_for_curtailment()

    # Priority 1 (Self-mining DG1+) should be first on the curtailment list
    assert sorted_batches[0].batch_id == "self_dg1_plus"
    # Priority 10 (Client S21+) should be last on the curtailment list (protected)
    assert sorted_batches[-1].batch_id == "client_s21_plus"
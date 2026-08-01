from gridyield.utils.data_generator import SyntheticDataGenerator

def test_annual_data_generator_shape_and_hydro_limits():
    generator = SyntheticDataGenerator(year=2026, baseline_kw=20000.0)
    df = generator.generate_annual_series()

    # 1. Assert length (2026 is a standard year with 8,760 hours)
    assert len(df) == 8760

    # 2. Assert dry season hydro throttling (Jan-April should average lower power than Aug)
    jan_avg_power = df.loc["2026-01", "kw_draw"].mean()
    aug_avg_power = df.loc["2026-08", "kw_draw"].mean()

    assert jan_avg_power < aug_avg_power
    assert jan_avg_power < 20000.0 * 0.88  # Significantly throttled during dry months

    # 3. Assert ambient temperature is within logical bounds
    assert df["ambient_temp_celsius"].min() > 10.0
    assert df["ambient_temp_celsius"].max() < 40.0
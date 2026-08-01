import numpy as np
import pandas as pd
from datetime import datetime

class SyntheticDataGenerator:
    """
    Generates 8,760 hours (1 full year) of realistic facility time-series data,
    including seasonal hydro availability factors, ambient temperature profiles,
    and grid stability curtailment events.
    """
    def __init__(self, year: int = 2026, baseline_kw: float = 20000.0, seed: int = 42):
        self.year = year
        self.baseline_kw = baseline_kw
        self.seed = seed
        np.random.seed(seed)

    def generate_annual_series(self) -> pd.DataFrame:
        """
        Generates 8,760 hourly time-series records for an entire year.
        Includes:
        - Hydro availability factor (Seasonal dry season drops in Jan-April)
        - Dynamic ambient temperature (°C)
        - Grid curtailment flags (Random grid maintenance / frequency drops)
        """
        start_date = f"{self.year}-01-01 00:00:00"
        end_date = f"{self.year}-12-31 23:00:00"
        dates = pd.date_range(start=start_date, end=end_date, freq="1h")

        df = pd.DataFrame(index=dates)
        hours = len(df) # 8,784 for leap year 2026 or 8,760 standard

        # 1. Seasonal Hydro Availability Factor
        # Months 1 to 4 (Jan-Apr) = Dry Season (Hydro reservoirs drop to 70-85% capacity)
        # Months 6 to 9 (Jun-Sep) = Wet / Rainy Season (100% capacity)
        month_array = df.index.month.values
        
        # Base seasonal curve
        hydro_factor = np.where(
            np.isin(month_array, [1, 2, 3, 4]),
            np.random.uniform(0.70, 0.85, hours),  # Dry season constraint
            np.where(
                np.isin(month_array, [6, 7, 8, 9]),
                1.00,  # Full wet season hydro output
                np.random.uniform(0.88, 0.98, hours)  # Shoulder transition months
            )
        )

        # 2. Daily Ambient Temperature Profile (°C)
        # Diurnal temperature cycle peaking around 14:00 daily
        hour_array = df.index.hour.values
        temp_base = 22.0 + 6.0 * np.sin((hour_array - 9) * np.pi / 12)
        ambient_temp = temp_base + np.random.normal(0, 1.5, hours)

        # 3. Unscheduled Grid Maintenance Outages (~1.5% random probability)
        random_outage_mask = np.random.binomial(1, 0.015, hours) == 1
        
        # Calculate available grid power draw (kW)
        available_grid_kw = self.baseline_kw * hydro_factor
        available_grid_kw[random_outage_mask] = 0.0  # Total zero-power outage

        df["kw_draw"] = available_grid_kw
        df["hydro_availability_factor"] = hydro_factor
        df["ambient_temp_celsius"] = np.round(ambient_temp, 2)
        df["is_grid_outage"] = random_outage_mask

        return df
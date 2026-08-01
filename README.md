# ⚡ GridYield AI: Facility Dispatch & Fleet Margin Engine

**GridYield AI** is an advanced, vectorized simulation engine and financial dispatch platform designed for grid-tied cryptocurrency mining operations, industrial data centers, and multi-tenant hosting facilities.

It bridges the gap between **power utility physics** (high-voltage step-down losses, time-of-use tariffs, seasonal hydro availability) and **crypto mining economics** (live network hashprice, hardware efficiency curves, tiered hosting SLAs).

---

## 🌟 Key Features

* **🔌 Physics-Grounded Tariff Engine**
  * Account for High-Voltage (HV) to Low-Voltage (LV) **transformer step-down losses** (e.g., 2.0%).
  * Value-Added Tax (**VAT**) and regional utility tax additions (e.g., 15% EEP Hydro tariff).
  * Flexible **Time-of-Use (TOU) load caps** and dynamic time-window curtailments.

* **🛡️ Tiered Priority Curtailment & Multi-Batch Fleet Management**
  * Model heterogeneous hardware fleets simultaneously (e.g., Antminer S21+, T21, DG1+).
  * **Automated Client Protection:** Prioritizes shedding lower-priority or self-mining hardware during grid capacity limits to protect high-priority hosting clients and uphold SLA uptime guarantees.
  * Explicitly distinguishes between capacity-driven load limits (`CURTAIL_CAP`) and financial breakeven cut-offs (`CURTAIL_UNPROFITABLE`).

* **🌊 8,760-Hour Hydrology & Seasonal Backtester**
  * Simulates a continuous 365-day hourly dataset (8,760 hours).
  * Models real-world seasonal hydro reservoir constraints (e.g., dry-season capacity throttling) and diurnal ambient temperature fluctuations.

* **📊 Executive Web UI & CLI Scenario Runner**
  * **Interactive Streamlit Dashboard (`app.py`):** Dynamic fleet editor, live sliders for Hashprice, tariff rates, and flexible curtailment window selectors (e.g., 6 PM – 9 PM evening peak).
  * **Command-Line Interface (`cli.py`):** Parse site YAML configuration files, execute multi-day or full annual backtests, and export structured CSV operational reports.

---

## 📁 Repository Structure

```text
gridyield-ai/
├── config/
│   └── sample_site.yaml             # Sample site config (tariffs, hardware, economics)
├── src/
│   └── gridyield/
│       ├── engine/
│       │   ├── tariff_engine.py      # HV/LV transformer losses, VAT, and TOU caps
│       │   └── profitability_engine.py # Multi-batch dispatch & priority curtailment
│       ├── schemas/
│       │   ├── economics.py         # Network economics schemas (Hashprice)
│       │   ├── fleet.py             # Hardware batch & site fleet schemas
│       │   └── tariff.py            # Tariff structure & TOU period schemas
│       ├── utils/
│       │   └── data_generator.py    # 8,760h annual hydro & temp time-series generator
│       └── cli.py                   # Command-line scenario runner
├── tests/                           # Pytest verification suites
│   ├── test_data_generator.py
│   ├── test_fleet_schema.py
│   ├── test_multi_batch_engine.py
│   └── test_tariff_engine.py
├── app.py                           # Interactive Streamlit Web UI
├── pyproject.toml                   # Project metadata & build settings
└── README.md                        # Documentation
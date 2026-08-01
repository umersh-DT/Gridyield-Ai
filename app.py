import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / "src"))
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from gridyield.schemas.tariff import TariffStructure, TimeOfUsePeriod
from gridyield.schemas.economics import NetworkEconomics
from gridyield.schemas.fleet import SiteFleetConfig, HardwareBatch, OwnershipType
from gridyield.engine.tariff_engine import TariffEngine
from gridyield.engine.profitability_engine import MultiBatchProfitabilityEngine
from gridyield.utils.data_generator import SyntheticDataGenerator

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="GridYield AI - Executive Dispatch & Profitability",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ GridYield AI: Facility Dispatch & Fleet Margin Engine")
st.markdown("Dynamic financial modeling and tiered curtailment simulation for grid-tied mining facilities.")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("🕹️ Facility & Grid Controls")

# 1. Network Economics
st.sidebar.subheader("1. Network Economics")
hashprice_input = st.sidebar.number_input(
    "Hashprice ($/TH/day)",
    min_value=0.0100,
    max_value=0.2000,
    value=0.0550,
    step=0.0050,
    format="%.4f"
)

# 2. Tariff & Loss Settings
st.sidebar.subheader("2. Grid Tariff & Losses")
base_rate = st.sidebar.number_input("Base Power Rate ($/kWh)", min_value=0.010, max_value=0.200, value=0.0316, step=0.002, format="%.4f")
vat_rate = st.sidebar.slider("VAT / Tax Rate (%)", min_value=0, max_value=25, value=15) / 100.0
transformer_loss = st.sidebar.slider("Transformer Loss (%)", min_value=0.0, max_value=5.0, value=2.0, step=0.5) / 100.0

# 3. Flexible Curtailment & Uptime Controls
st.sidebar.subheader("3. Grid Curtailment & Uptime Profile")
curtailment_mode = st.sidebar.selectbox(
    "Grid Restriction Profile",
    ["Custom Peak Hours Cap", "Flat Capacity Restriction (e.g. 90% / 23% Uptime)", "Continuous 100% Full Power"]
)

cap_start_hour, cap_end_hour = 10, 16
allowed_load_pct = 1.00

if curtailment_mode == "Custom Peak Hours Cap":
    cap_start_hour, cap_end_hour = st.sidebar.slider(
        "Curtailment Hours Window (24h Clock)",
        min_value=0, max_value=23, value=(18, 21), help="e.g. 18 to 21 = 6 PM to 9 PM Evening Peak"
    )
    allowed_load_pct = st.sidebar.slider("Allowed Capacity during Curtailment (%)", min_value=0, max_value=100, value=50) / 100.0

elif curtailment_mode == "Flat Capacity Restriction (e.g. 90% / 23% Uptime)":
    allowed_load_pct = st.sidebar.slider("Flat Grid Capacity Limit (%)", min_value=5, max_value=100, value=90) / 100.0
    cap_start_hour, cap_end_hour = 0, 23

# 4. Simulation Horizon
st.sidebar.subheader("4. Simulation Timeframe")
sim_mode = st.sidebar.radio("Time Horizon", ["24-Hour Daily Sample", "Full Annual (8,760 Hours)"])
is_annual_mode = (sim_mode == "Full Annual (8,760 Hours)")

# --- MAIN PAGE: DYNAMIC FLEET CONFIGURATOR ---
with st.expander("🛠️ Dynamic Hardware Fleet Configurator (Click to Edit Machines)", expanded=False):
    st.markdown("Customize hardware models, unit counts, power draw, and client vs. self-mining priority tiers for your site.")
    
    default_batches = pd.DataFrame([
        {"Batch ID": "client_s21", "Model": "Antminer S21+", "Ownership": "CLIENT", "Units": 2000, "TH/Unit": 235.0, "kW/Unit": 3.87, "Priority": 10},
        {"Batch ID": "client_t21", "Model": "Antminer T21", "Ownership": "CLIENT", "Units": 2000, "TH/Unit": 190.0, "kW/Unit": 3.61, "Priority": 5},
        {"Batch ID": "self_dg1", "Model": "DG1+", "Ownership": "SELF_MINING", "Units": 500, "TH/Unit": 11.0, "kW/Unit": 3.40, "Priority": 1}
    ])

    edited_fleet_df = st.data_editor(
        default_batches,
        num_rows="dynamic",
        column_config={
            "Ownership": st.column_config.SelectboxColumn("Ownership", options=["CLIENT", "SELF_MINING"]),
            "Priority": st.column_config.NumberColumn("Priority Tier (1=Curtail First, 10=Protect Last)", min_value=1, max_value=10)
        },
        use_container_width=True
    )

# --- CONVERT EDITED FLEET TO SCHEMAS ---
batches_list = []
for _, row in edited_fleet_df.iterrows():
    try:
        batches_list.append(
            HardwareBatch(
                batch_id=str(row["Batch ID"]),
                model_name=str(row["Model"]),
                ownership=OwnershipType.CLIENT if row["Ownership"] == "CLIENT" else OwnershipType.SELF_MINING,
                unit_count=int(row["Units"]),
                hashrate_per_unit_th=float(row["TH/Unit"]),
                power_per_unit_kw=float(row["kW/Unit"]),
                curtailment_priority=int(row["Priority"])
            )
        )
    except Exception as e:
        st.error(f"Error in batch entry '{row.get('Batch ID', 'Unknown')}': {e}")

site_fleet = SiteFleetConfig(
    site_id="ethiopia_substation_alpha",
    contracted_grid_capacity_kw=sum(b.total_batch_power_kw for b in batches_list) or 20000.0,
    batches=batches_list
)

# --- ENGINE EXECUTION ---
@st.cache_data
def run_simulation_engine(hashprice, base_rate, vat, loss, start_hr, end_hr, cap_pct, is_annual, fleet_dict):
    # Setup Tariff
    tou_periods = []
    if cap_pct < 1.0 or start_hr != end_hr:
        tou_periods.append(TimeOfUsePeriod(
            name="Grid Curtailment Cap",
            rate_per_kwh=base_rate,
            start_hour=start_hr,
            end_hour=end_hr,
            allowed_load_pct=cap_pct
        ))

    tariff = TariffStructure(
        contract_name="EEP Grid Contract",
        base_rate_per_kwh=base_rate,
        tax_rate_pct=vat,
        transformer_loss_pct=loss,
        tou_periods=tou_periods
    )

    economics = NetworkEconomics(hashprice_usd_per_th_day=hashprice)

    # Generate Time-Series Input
    if is_annual:
        gen = SyntheticDataGenerator(year=2026, baseline_kw=site_fleet.total_fleet_power_kw)
        input_df = gen.generate_annual_series()
    else:
        dates = pd.date_range("2026-08-01 00:00", periods=24, freq="1h")
        input_df = pd.DataFrame({"kw_draw": [site_fleet.total_fleet_power_kw] * 24}, index=dates)

    tariff_engine = TariffEngine(tariff, facility_contract_kw=site_fleet.contracted_grid_capacity_kw)
    tariff_df = tariff_engine.process_power_series(input_df)

    profit_engine = MultiBatchProfitabilityEngine(site_fleet, economics)
    results_df = profit_engine.calculate_site_profitability(tariff_df)

    return results_df

# Convert fleet to serializable dict for st.cache_data
fleet_serialized = [b.model_dump() for b in site_fleet.batches]
results_df = run_simulation_engine(
    hashprice_input, base_rate, vat_rate, transformer_loss,
    cap_start_hour, cap_end_hour, allowed_load_pct, is_annual_mode, fleet_serialized
)

# --- HEADER EXECUTIVE KPI METRICS ---
st.divider()

total_rev = results_df["site_gross_revenue_usd"].sum()
total_cost = results_df["site_power_expense_usd"].sum()
net_margin = results_df["site_net_margin_usd"].sum()
total_hours = len(results_df)

daily_rev = (total_rev / total_hours) * 24
daily_cost = (total_cost / total_hours) * 24
daily_margin = (net_margin / total_hours) * 24

col1, col2, col3, col4 = st.columns(4)

if is_annual_mode:
    col1.metric("Gross Revenue (Annual)", f"${total_rev:,.2f}", f"${daily_rev:,.2f} / day")
    col2.metric("Power Expense (Annual)", f"${total_cost:,.2f}", f"${daily_cost:,.2f} / day")
    col3.metric("Net Margin (Annual)", f"${net_margin:,.2f}", f"${daily_margin:,.2f} / day")
else:
    col1.metric("Daily Gross Revenue", f"${daily_rev:,.2f}", f"${daily_rev/24:,.2f} / hr")
    col2.metric("Daily Power Expense", f"${daily_cost:,.2f}", f"${daily_cost/24:,.2f} / hr")
    col3.metric("Daily Net Margin", f"${daily_margin:,.2f}", f"${daily_margin/24:,.2f} / hr")

col4.metric("Active Site Load / Capacity", f"{site_fleet.total_fleet_power_kw / 1000:,.1f} MW", f"{site_fleet.total_fleet_hashrate_th / 1000:,.1f} PH/s")

# --- CHARTS SECTION ---
st.divider()
st.subheader("📊 Dispatch & Fleet Power Allocation")

# Delivered Power Allocation Chart
power_cols = [col for col in results_df.columns if col.startswith("delivered_kw_")]
power_df = results_df[power_cols].copy()
power_df.columns = [col.replace("delivered_kw_", "").upper() for col in power_df.columns]

fig_power = px.line(
    power_df, 
    y=power_df.columns, 
    title="Delivered Power Draw per Batch (kW)",
    labels={"value": "Delivered Power (kW)", "index": "Timestamp", "variable": "Hardware Batch"}
)
st.plotly_chart(fig_power, use_container_width=True)

col_left, col_right = st.columns(2)

with col_left:
    fig_margin = px.area(
        results_df, 
        y="site_net_margin_usd", 
        title="Hourly Net Hosting Margin ($)",
        labels={"site_net_margin_usd": "Net Margin ($)"},
        color_discrete_sequence=["#00CC96"]
    )
    st.plotly_chart(fig_margin, use_container_width=True)

with col_right:
    fig_tariff = px.line(
        results_df, 
        y="effective_rate_per_kwh", 
        title="Effective Electricity Cost ($/kWh incl. Losses & VAT)",
        labels={"effective_rate_per_kwh": "Rate ($/kWh)"},
        color_discrete_sequence=["#EF553B"]
    )
    st.plotly_chart(fig_tariff, use_container_width=True)

# --- CLEAN EXECUTIVE DATA TABLE ---
st.divider()
st.subheader("📄 Executive Hourly Operations Table")

# Create simple, business-friendly dataframe
exec_df = pd.DataFrame(index=results_df.index)

# Business Status Logic
def derive_status(row):
    if row["delivered_kw"] == 0:
        return "🔴 Outage / Zero Grid Capacity"
    elif row["delivered_kw"] < row["kw_draw"] * 0.99:
        return "🟡 Curtailed (Capacity Limit)"
    else:
        return "🟢 Full Power Run"

exec_df["Grid Status"] = results_df.apply(derive_status, axis=1)
exec_df["Total Delivered Power (MW)"] = (results_df["delivered_kw"] / 1000.0).round(2)
exec_df["Effective Rate ($/kWh)"] = results_df["effective_rate_per_kwh"].round(4)
exec_df["Gross Revenue ($)"] = results_df["site_gross_revenue_usd"].round(2)
exec_df["Power Expense ($)"] = results_df["site_power_expense_usd"].round(2)
exec_df["Net Margin ($)"] = results_df["site_net_margin_usd"].round(2)

show_technical = st.checkbox("Show Advanced Technical Engine Columns")

if show_technical:
    st.dataframe(results_df, height=350, use_container_width=True)
else:
    st.dataframe(exec_df, height=350, use_container_width=True)

# Download CSV Export
csv_data = results_df.to_csv().encode('utf-8')
st.download_button(
    label="📥 Download Detailed Hourly Report (CSV)",
    data=csv_data,
    file_name="gridyield_hourly_dispatch_report.csv",
    mime="text/csv"
)
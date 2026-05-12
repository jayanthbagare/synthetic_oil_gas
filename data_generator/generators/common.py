"""Shared RNG helpers, vocabularies, and lookup tables for all generators."""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# RNG helpers
# ---------------------------------------------------------------------------

def make_rng(master: np.random.Generator, index: int) -> np.random.Generator:
    """Spawn a deterministic child RNG from the master using SeedSequence."""
    seed_seq = np.random.SeedSequence(master.bit_generator.state["state"]["state"])
    children = seed_seq.spawn(index + 1)
    return np.random.default_rng(children[index])


# ---------------------------------------------------------------------------
# Asset classes
# ---------------------------------------------------------------------------

ASSET_CLASSES: list[str] = [
    "centrifugal_pump",
    "reciprocating_pump",
    "compressor",
    "heat_exchanger",
    "fired_heater",
    "column",
    "vessel",
    "control_valve",
    "isolation_valve",
    "instrument",
    "piping",
    "electrical_motor",
    "transformer",
    "cooling_tower",
    "flare",
]

# Approximate share of the 500-asset fleet
ASSET_CLASS_WEIGHTS: dict[str, float] = {
    "centrifugal_pump":   0.18,
    "reciprocating_pump": 0.08,
    "compressor":         0.06,
    "heat_exchanger":     0.14,
    "fired_heater":       0.03,
    "column":             0.04,
    "vessel":             0.08,
    "control_valve":      0.12,
    "isolation_valve":    0.10,
    "instrument":         0.10,
    "piping":             0.06,
    "electrical_motor":   0.05,
    "transformer":        0.02,
    "cooling_tower":      0.02,
    "flare":              0.02,
}

# MTBF ranges (days) by asset class: (low, high)
MTBF_RANGES: dict[str, tuple[int, int]] = {
    "centrifugal_pump":   (180, 280),
    "reciprocating_pump": (200, 320),
    "compressor":         (250, 400),
    "heat_exchanger":     (365, 550),
    "fired_heater":       (400, 600),
    "column":             (500, 730),
    "vessel":             (450, 700),
    "control_valve":      (730, 1095),
    "isolation_valve":    (900, 1460),
    "instrument":         (730, 1095),
    "piping":             (600, 900),
    "electrical_motor":   (365, 600),
    "transformer":        (730, 1460),
    "cooling_tower":      (400, 600),
    "flare":              (600, 900),
}

# Replacement cost ranges (USD) by asset class: (low, high)
REPLACEMENT_COST_RANGES: dict[str, tuple[int, int]] = {
    "centrifugal_pump":   (50_000,   500_000),
    "reciprocating_pump": (80_000,   800_000),
    "compressor":         (200_000, 3_000_000),
    "heat_exchanger":     (100_000, 1_500_000),
    "fired_heater":       (500_000, 5_000_000),
    "column":             (300_000, 4_000_000),
    "vessel":             (100_000, 2_000_000),
    "control_valve":      (10_000,   200_000),
    "isolation_valve":    (5_000,    100_000),
    "instrument":         (500,       50_000),
    "piping":             (10_000,   300_000),
    "electrical_motor":   (20_000,   500_000),
    "transformer":        (100_000, 2_000_000),
    "cooling_tower":      (200_000, 1_500_000),
    "flare":              (50_000,   500_000),
}

# Criticality multiplier on replacement cost
CRITICALITY_COST_MULTIPLIER: dict[int, float] = {1: 2.0, 2: 1.4, 3: 1.0, 4: 0.7, 5: 0.4}

# Criticality effect on MTBF (T1 fails more often)
CRITICALITY_MTBF_MULTIPLIER: dict[int, float] = {1: 0.65, 2: 0.85, 3: 1.0, 4: 1.15, 5: 1.30}


# ---------------------------------------------------------------------------
# Failure categories
# ---------------------------------------------------------------------------

FAILURE_CATEGORIES: list[str] = [
    "leak",
    "vibration_abnormal",
    "temperature_high",
    "pressure_abnormal",
    "flow_abnormal",
    "control_drift",
    "instrument_failure",
    "lubrication_low",
    "seal_failure",
    "bearing_wear",
    "coupling_misalignment",
    "process_fouling",
    "corrosion",
    "electrical_fault",
    "false_positive",
    "duplicate",
]

# Characteristic failure modes per asset class (weights sum need not be 1; normalised at use)
ASSET_FAILURE_MODES: dict[str, dict[str, float]] = {
    "centrifugal_pump": {
        "seal_failure": 0.30, "bearing_wear": 0.25, "coupling_misalignment": 0.15,
        "vibration_abnormal": 0.15, "leak": 0.10, "lubrication_low": 0.05,
    },
    "reciprocating_pump": {
        "seal_failure": 0.28, "bearing_wear": 0.20, "vibration_abnormal": 0.18,
        "leak": 0.15, "lubrication_low": 0.10, "coupling_misalignment": 0.09,
    },
    "compressor": {
        "vibration_abnormal": 0.30, "bearing_wear": 0.25, "temperature_high": 0.20,
        "seal_failure": 0.15, "lubrication_low": 0.10,
    },
    "heat_exchanger": {
        "process_fouling": 0.40, "leak": 0.25, "corrosion": 0.20,
        "temperature_high": 0.10, "flow_abnormal": 0.05,
    },
    "fired_heater": {
        "temperature_high": 0.35, "leak": 0.25, "corrosion": 0.20,
        "flow_abnormal": 0.10, "instrument_failure": 0.10,
    },
    "column": {
        "corrosion": 0.30, "leak": 0.25, "process_fouling": 0.25,
        "pressure_abnormal": 0.10, "instrument_failure": 0.10,
    },
    "vessel": {
        "corrosion": 0.35, "leak": 0.25, "process_fouling": 0.20,
        "pressure_abnormal": 0.12, "instrument_failure": 0.08,
    },
    "control_valve": {
        "leak": 0.35, "control_drift": 0.35, "instrument_failure": 0.20,
        "flow_abnormal": 0.10,
    },
    "isolation_valve": {
        "leak": 0.55, "control_drift": 0.20, "corrosion": 0.15,
        "instrument_failure": 0.10,
    },
    "instrument": {
        "instrument_failure": 0.55, "control_drift": 0.30,
        "electrical_fault": 0.10, "flow_abnormal": 0.05,
    },
    "piping": {
        "leak": 0.45, "corrosion": 0.35, "pressure_abnormal": 0.15,
        "flow_abnormal": 0.05,
    },
    "electrical_motor": {
        "electrical_fault": 0.40, "bearing_wear": 0.30,
        "vibration_abnormal": 0.20, "lubrication_low": 0.10,
    },
    "transformer": {
        "electrical_fault": 0.70, "temperature_high": 0.20,
        "instrument_failure": 0.10,
    },
    "cooling_tower": {
        "process_fouling": 0.35, "flow_abnormal": 0.30,
        "corrosion": 0.20, "leak": 0.15,
    },
    "flare": {
        "leak": 0.45, "temperature_high": 0.30,
        "corrosion": 0.15, "instrument_failure": 0.10,
    },
}


# ---------------------------------------------------------------------------
# Location units
# ---------------------------------------------------------------------------

LOCATION_UNITS: list[str] = [
    "Crude_Distillation",
    "Catalytic_Cracking",
    "Hydrotreating",
    "Reforming",
    "Utilities",
    "Tankage",
]

# Asset name pools by (asset_class, location_unit) — sampled with replacement + suffix
ASSET_NAME_TEMPLATES: dict[str, list[str]] = {
    "centrifugal_pump":   ["Charge Pump", "Reflux Pump", "Product Pump", "Circulation Pump",
                           "Feed Pump", "Booster Pump", "Transfer Pump"],
    "reciprocating_pump": ["Injection Pump", "Chemical Dosing Pump", "High-Pressure Feed Pump",
                           "Metering Pump", "Wash Water Pump"],
    "compressor":         ["Recycle Gas Compressor", "Makeup Gas Compressor", "Wet Gas Compressor",
                           "Air Compressor", "Instrument Air Compressor", "Refrigeration Compressor"],
    "heat_exchanger":     ["Feed/Effluent Exchanger", "Overhead Condenser", "Reboiler",
                           "Product Cooler", "Preheater", "Intercooler", "Trim Cooler"],
    "fired_heater":       ["Charge Heater", "Reboiler Furnace", "Reformer Furnace",
                           "Process Heater", "Hot Oil Heater"],
    "column":             ["Atmospheric Tower", "Vacuum Tower", "Stripper Column",
                           "Absorber Column", "Splitter Column", "Fractionator"],
    "vessel":             ["Flash Drum", "Separator", "Surge Drum", "Accumulator",
                           "Knockout Drum", "Coalescer"],
    "control_valve":      ["Flow Control Valve", "Pressure Control Valve", "Level Control Valve",
                           "Temperature Control Valve", "Backpressure Valve"],
    "isolation_valve":    ["Block Valve", "Shutdown Valve", "Check Valve",
                           "Emergency Isolation Valve", "Gate Valve"],
    "instrument":         ["Flow Transmitter", "Pressure Transmitter", "Temperature Element",
                           "Level Gauge", "Analyzer", "Flow Meter"],
    "piping":             ["Process Header", "Cooling Water Supply Line", "Steam Line",
                           "Drain Line", "Vent Line", "Utility Cross-connect"],
    "electrical_motor":   ["Pump Drive Motor", "Compressor Drive Motor", "Fan Motor",
                           "Agitator Motor", "Conveyor Motor"],
    "transformer":        ["Main Power Transformer", "Unit Substation Transformer",
                           "Lighting Transformer", "MCC Feed Transformer"],
    "cooling_tower":      ["Cooling Tower Cell", "Cooling Tower Fan", "Cooling Tower Basin"],
    "flare":              ["Elevated Flare", "Ground Flare", "Flare KO Drum"],
}

ASSET_NAME_SUFFIXES: list[str] = ["A", "B", "C", "D", "1", "2", "3", "101", "102", "201", "202"]


# ---------------------------------------------------------------------------
# Notification raw-text templates
# Keys are ground_truth_category values.
# Placeholders: {asset_name}, {unit}, {value}, {baseline}, {shift}
# Styles: terse | verbose | misleading
# ---------------------------------------------------------------------------

RAW_TEXT_TEMPLATES: dict[str, list[str]] = {
    "seal_failure": [
        # terse
        "{asset_name} seal weep noted on walkdown.",
        "Seal leak on {asset_name} — small drip from stuffing box.",
        # verbose
        "Operator on {shift} shift reports fluid weeping from the mechanical seal on {asset_name} "
        "in {unit}. Rate appears to be increasing since first observed. Recommend inspection.",
        "Maintenance crew observed steady drip from {asset_name} seal area during PM rounds. "
        "Fluid on the drip tray. Asset still operating within limits but seal is degrading.",
        # misleading (symptom, not root cause)
        "Puddle forming under {asset_name} — possible drain valve passing or line drain.",
    ],
    "bearing_wear": [
        "High bearing temp on {asset_name} — {value}°C vs normal {baseline}°C.",
        "{asset_name} bearing housing warm to the touch during rounds.",
        "Abnormal noise from {asset_name} bearing area — grinding / rumbling sound noted by "
        "day shift operator. Has been getting worse over last few days.",
        "{asset_name} vibration slowly trending up over past week. Bearing wear suspected. "
        "Vibe reading now {value} mm/s.",
        # misleading
        "{asset_name} making unusual noise — could be cavitation or something in the suction line.",
    ],
    "vibration_abnormal": [
        "High vibe alarm on {asset_name}, {value} mm/s.",
        "{asset_name} overall vibration {value} mm/s — exceeded alarm setpoint.",
        "Abnormal vibration on {asset_name}. Day shift heard it first. Sounds mechanical. "
        "Reading now {value} mm/s vs normal baseline {baseline} mm/s. Could be cavitation "
        "or a coupling alignment issue — needs eyes on it.",
        "Operator on {shift} shift reports shaking / vibration on {asset_name} in {unit}. "
        "Started around 4 AM. Asset still running but vibe trending up.",
        # misleading
        "Unusual noise from {asset_name} area — could be nearby equipment vibrating.",
    ],
    "temperature_high": [
        "{asset_name} outlet temp high — {value}°C, alarm at {baseline}°C.",
        "High temp indication on {asset_name}.",
        "Operator notes {asset_name} running hotter than normal. Outlet temp {value}°C, "
        "setpoint {baseline}°C. Possible fouling or reduced cooling flow.",
        "{asset_name} skin temperature elevated — measured {value}°C on external IR scan. "
        "No change in process conditions. Internal fouling suspected.",
        # misleading (symptom is temp but real issue may be fouling)
        "{asset_name} not performing to spec — throughput OK but outlet temp creeping up.",
    ],
    "pressure_abnormal": [
        "{asset_name} pressure reading erratic — swinging ±{value} psi.",
        "High differential pressure across {asset_name} — {value} psi vs normal {baseline} psi.",
        "Operator reports {asset_name} pressure alarm active. DP {value} psi and climbing. "
        "Suction strainer may be plugging.",
        "{asset_name} suction pressure low — {value} psi. Checked upstream block valves, "
        "all open. Source of pressure drop unclear.",
        # misleading
        "{asset_name} not flowing well — performance drop. Pressure may be a symptom.",
    ],
    "flow_abnormal": [
        "{asset_name} flow low — {value} m³/h, expected {baseline} m³/h.",
        "Flow meter on {asset_name} reading low. Possible instrument issue or actual flow loss.",
        "Reduced throughput on {asset_name} noted by control room. Flow {value} m³/h vs "
        "design {baseline} m³/h. Plugging or partial valve closure suspected.",
        "{asset_name} flow oscillating — swinging between {baseline} and {value} m³/h. "
        "Control valve hunting possible.",
        # misleading
        "Production rate drop on {unit} unit — may be related to {asset_name} performance.",
    ],
    "control_drift": [
        "{asset_name} valve position drifting — not tracking setpoint.",
        "Control loop on {asset_name} unstable — hunting ±{value}%.",
        "Operator had to switch {asset_name} to manual — auto mode causing oscillations. "
        "Valve positioner may need recalibration.",
        "{asset_name} not holding setpoint in auto. Offset of {value} units from SP. "
        "Instrument check recommended.",
        # misleading
        "{asset_name} area running poorly — process keeps drifting off target.",
    ],
    "instrument_failure": [
        "{asset_name} transmitter reading stuck at {value}.",
        "{asset_name} instrument giving spurious readings — not credible.",
        "Field instrument on {asset_name} failed. Reading pegged at {value} even with "
        "process conditions changed. Likely transmitter failure.",
        "{asset_name} indicator showing bad tag — control room has flagged it. "
        "Last good reading was {baseline}.",
        # misleading
        "Can't tell what {asset_name} is doing — all readings seem off in that area.",
    ],
    "lubrication_low": [
        "{asset_name} lube oil level low — topped up during rounds.",
        "Low lube oil pressure alarm on {asset_name} — {value} psi vs low alarm {baseline} psi.",
        "Operator found {asset_name} lube oil reservoir below low-level mark. "
        "No visible external leak. Internal consumption or seal passing.",
        "{asset_name} oil analysis shows high wear metals — Fe {value} ppm. "
        "Lube system inspection required.",
        # misleading
        "{asset_name} running rough — noise and slight vibration, possibly lubrication related.",
    ],
    "coupling_misalignment": [
        "{asset_name} coupling showing signs of wear / misalignment.",
        "Coupling guard on {asset_name} warm — possible misalignment.",
        "After last PM on {asset_name}, vibration has been slightly elevated. "
        "Coupling alignment check recommended — vibe signature consistent with angular misalignment.",
        "{asset_name} producing high 1× and 2× vibe harmonics. Soft foot or misalignment suspected.",
        # misleading
        "{asset_name} started vibrating after maintenance last week — cause unknown.",
    ],
    "process_fouling": [
        "{asset_name} differential pressure rising — fouling suspected.",
        "Heat duty dropping on {asset_name} — clean up required.",
        "{asset_name} showing classic fouling signature — DP up {value} psi, "
        "heat duty down {baseline}%. Has been trending for 3 weeks.",
        "Reduced performance on {asset_name}. Outlet temperature elevated and DP increasing. "
        "Due for cleaning per maintenance schedule.",
        # misleading
        "Temperature high on {asset_name} outlet — could be reduced cooling or fouling.",
    ],
    "corrosion": [
        "Corrosion found on {asset_name} during inspection — wall thickness low.",
        "Pitting corrosion noted on {asset_name} external surface.",
        "Inspection crew found external corrosion on {asset_name} in {unit}. "
        "Corrosion under insulation (CUI) suspected. Requires UT scan to assess wall thickness.",
        "Paint breakdown and rust observed on {asset_name} during walkaround. "
        "Surface preparation and recoating required.",
        # misleading
        "{asset_name} showing some deterioration — unclear if structural or cosmetic.",
    ],
    "electrical_fault": [
        "{asset_name} motor tripped on electrical fault — OLR/breaker open.",
        "Ground fault indicator on {asset_name} MCC active.",
        "Electrical trip on {asset_name}. Control room shows motor protection relay operated. "
        "Ground fault suspected. Requires electrical inspection before restart.",
        "{asset_name} motor running hot — winding temp {value}°C vs trip setpoint {baseline}°C. "
        "Possible insulation degradation.",
        # misleading
        "{asset_name} stopped unexpectedly — may be electrical or process interlock.",
    ],
    "leak": [
        "Leak on {asset_name} — small drip from flange.",
        "{asset_name} flange weeping — steam/product visible.",
        "Operator found fluid on ground under {asset_name} in {unit}. "
        "Appears to be a flange or fitting leak. Rate about {value} drips/min.",
        "{asset_name} showing a seep at the body-to-bonnet joint. "
        "Flagged by inspection on routine walkdown.",
        # misleading
        "Smell of product near {asset_name} — source not confirmed yet.",
    ],
    "false_positive": [
        "{asset_name} vibration alarm active — checked field, unit running normally.",
        "Temperature indicator on {asset_name} reading high — local gauge confirms normal.",
        "Operator reported unusual noise from {asset_name} area. "
        "Investigated — noise was from adjacent scaffolding work. No defect found.",
        "{asset_name} flow reading low. Control room check showed instrument connection "
        "had been bumped during housekeeping. Reading restored to normal.",
        "Level alarm on {asset_name} triggered. Field check shows level normal — "
        "instrument calibration drift suspected. Reading within 2% after re-zero.",
    ],
    "duplicate": [
        "{asset_name} seal leak — follow-up to earlier notification.",
        "Same vibration issue on {asset_name} reported again by night shift.",
        "Re-notification: {asset_name} still showing high temp — previous ticket still open.",
        "Ongoing issue with {asset_name} — another report from field crew.",
        "{asset_name} problem from yesterday still not resolved — raising again.",
    ],
}

# Shift names used in templates
SHIFT_NAMES: list[str] = ["day", "night", "back"]

# Plausible numeric value ranges for template placeholders
TEMPLATE_VALUES: dict[str, tuple[float, float]] = {
    "vibe_mm_s":      (4.5, 18.0),
    "vibe_baseline":  (1.5, 3.5),
    "temp_c":         (85.0, 180.0),
    "temp_baseline":  (60.0, 80.0),
    "pressure_psi":   (15.0, 80.0),
    "pressure_base":  (8.0, 14.0),
    "flow_m3h":       (20.0, 120.0),
    "flow_base":      (80.0, 150.0),
    "valve_pct":      (5.0, 25.0),
    "fe_ppm":         (80.0, 400.0),
    "winding_c":      (140.0, 175.0),
    "winding_base":   (180.0, 200.0),
    "drip_min":       (3.0, 30.0),
    "dp_psi":         (8.0, 40.0),
    "dp_base":        (3.0, 7.0),
    "heat_duty_pct":  (10.0, 35.0),
    "stuck_value":    (0.0, 100.0),
    "last_good":      (20.0, 95.0),
}


# ---------------------------------------------------------------------------
# Permit definitions
# ---------------------------------------------------------------------------

PERMITS: list[dict] = [
    {"permit_code": "PMT-CW", "permit_name": "Cold Work",                    "typical_lead_time_hours": 1,  "prerequisites": ""},
    {"permit_code": "PMT-EI", "permit_name": "Energy Isolation (LOTO)",      "typical_lead_time_hours": 1,  "prerequisites": ""},
    {"permit_code": "PMT-VE", "permit_name": "Vehicle Entry",                "typical_lead_time_hours": 1,  "prerequisites": ""},
    {"permit_code": "PMT-WH", "permit_name": "Working at Height",            "typical_lead_time_hours": 2,  "prerequisites": ""},
    {"permit_code": "PMT-HW", "permit_name": "Hot Work",                     "typical_lead_time_hours": 2,  "prerequisites": "PMT-CW"},
    {"permit_code": "PMT-LB", "permit_name": "Line Break",                   "typical_lead_time_hours": 2,  "prerequisites": "PMT-EI"},
    {"permit_code": "PMT-BP", "permit_name": "Bypass",                       "typical_lead_time_hours": 2,  "prerequisites": "PMT-EI"},
    {"permit_code": "PMT-EX", "permit_name": "Excavation",                   "typical_lead_time_hours": 3,  "prerequisites": ""},
    {"permit_code": "PMT-CS", "permit_name": "Confined Space Entry",         "typical_lead_time_hours": 4,  "prerequisites": "PMT-EI"},
    {"permit_code": "PMT-RA", "permit_name": "Radiation",                    "typical_lead_time_hours": 8,  "prerequisites": "PMT-EI"},
]


# ---------------------------------------------------------------------------
# Part categories
# ---------------------------------------------------------------------------

PART_CATEGORIES: list[str] = [
    "bearing", "seal", "gasket", "valve_trim", "motor",
    "instrument", "lubricant", "coupling", "electrical", "fitting",
]

PART_CATEGORY_COMPATIBLE_CLASSES: dict[str, list[str]] = {
    "bearing":    ["centrifugal_pump", "reciprocating_pump", "compressor", "electrical_motor", "cooling_tower"],
    "seal":       ["centrifugal_pump", "reciprocating_pump", "compressor", "column", "vessel"],
    "gasket":     ["heat_exchanger", "column", "vessel", "piping", "fired_heater", "flare"],
    "valve_trim": ["control_valve", "isolation_valve"],
    "motor":      ["electrical_motor", "centrifugal_pump", "cooling_tower"],
    "instrument": ["instrument", "control_valve", "isolation_valve", "heat_exchanger"],
    "lubricant":  ["centrifugal_pump", "reciprocating_pump", "compressor", "electrical_motor"],
    "coupling":   ["centrifugal_pump", "reciprocating_pump", "compressor", "electrical_motor"],
    "electrical": ["electrical_motor", "transformer", "instrument"],
    "fitting":    ["piping", "heat_exchanger", "fired_heater", "column", "vessel"],
}

PART_CATEGORY_LEAD_TIME: dict[str, tuple[float, float]] = {
    # (mean_days, stdev_days)
    "bearing":    (4.0,  1.5),
    "seal":       (7.0,  2.5),
    "gasket":     (3.0,  1.0),
    "valve_trim": (45.0, 12.0),
    "motor":      (21.0, 7.0),
    "instrument": (14.0, 5.0),
    "lubricant":  (2.0,  0.5),
    "coupling":   (10.0, 3.0),
    "electrical": (7.0,  2.0),
    "fitting":    (5.0,  1.5),
}

PART_CATEGORY_COST: dict[str, tuple[float, float]] = {
    # (low_usd, high_usd) — uniform draw
    "bearing":    (50,      800),
    "seal":       (100,   2_000),
    "gasket":     (10,      500),
    "valve_trim": (500,  15_000),
    "motor":      (2_000, 50_000),
    "instrument": (200,   8_000),
    "lubricant":  (20,      200),
    "coupling":   (300,   5_000),
    "electrical": (100,   3_000),
    "fitting":    (20,    1_000),
}

# Representative part name roots per category
PART_NAME_ROOTS: dict[str, list[str]] = {
    "bearing":    ["Ball Bearing", "Roller Bearing", "Thrust Bearing", "Sleeve Bearing", "Journal Bearing"],
    "seal":       ["Mechanical Seal", "Lip Seal", "O-Ring Kit", "Shaft Seal", "Face Seal"],
    "gasket":     ["Spiral Wound Gasket", "Ring Joint Gasket", "Flat Gasket", "PTFE Gasket", "Sheet Gasket"],
    "valve_trim": ["Ball Valve Trim", "Gate Valve Trim", "Plug Valve Trim", "Globe Valve Trim", "Seat Ring Set"],
    "motor":      ["Induction Motor", "TEFC Motor", "Explosion-Proof Motor", "VFD-Ready Motor"],
    "instrument": ["Pressure Transmitter", "Flow Transmitter", "Level Transmitter", "Thermowell", "Gauge"],
    "lubricant":  ["Turbine Oil", "Gear Oil", "Compressor Oil", "Grease Cartridge", "Hydraulic Fluid"],
    "coupling":   ["Flexible Coupling", "Grid Coupling", "Jaw Coupling", "Disc Coupling", "Spacer Coupling"],
    "electrical": ["Circuit Breaker", "Contactor", "Relay", "Fuse Block", "Terminal Block"],
    "fitting":    ["Elbow Fitting", "Tee Fitting", "Reducer", "Union", "Flange Assembly"],
}


# ---------------------------------------------------------------------------
# Crew skill codes
# ---------------------------------------------------------------------------

SKILL_CODES: list[str] = [
    "mechanical", "rotating_equipment", "static_equipment", "welding",
    "electrical", "instrumentation", "rigging", "scaffolding",
    "confined_space", "hot_work", "inspection",
]

# Skill sets per crew type (indices into SKILL_CODES)
CREW_SKILL_PROFILES: list[list[str]] = [
    ["mechanical", "rotating_equipment"],
    ["mechanical", "rotating_equipment", "lubrication"],
    ["mechanical", "static_equipment", "welding"],
    ["mechanical", "static_equipment"],
    ["electrical", "instrumentation"],
    ["electrical"],
    ["instrumentation"],
    ["mechanical", "rotating_equipment", "electrical"],
    ["mechanical", "static_equipment", "rigging", "scaffolding"],
    ["mechanical", "rotating_equipment", "confined_space"],
    ["mechanical", "static_equipment", "hot_work", "welding"],
    ["inspection"],
]


# ---------------------------------------------------------------------------
# Downtime cost rates by criticality tier (USD/hour)
# Calibrated so rolling 12-month total ≈ $25–35M across the dataset.
# T1 rate reflects "$1–5M/day" plant-level impact (÷24 = $42k–$208k/hour).
# ---------------------------------------------------------------------------

DOWNTIME_COST_RATE: dict[int, tuple[float, float]] = {
    # Calibrated so rolling 12-month total ≈ $25–35M across ~600 failures/year.
    # T1: each failure affects one asset, typically causing partial rather than
    # total production disruption. Full-plant $1-5M/day ÷ 30 T1 assets ÷ 24h ≈ per-asset rate.
    1: (20_000.0,   80_000.0),
    2:  (5_000.0,   25_000.0),
    3:  (1_000.0,    5_000.0),
    4:    (200.0,    1_000.0),
    5:      (0.0,      200.0),
}


# ---------------------------------------------------------------------------
# Work-order permit mapping by asset class + work type
# ---------------------------------------------------------------------------

def required_permits_for(asset_class: str, work_type: str) -> list[str]:
    """Return a plausible list of permit codes for a given asset/work combination."""
    permits: set[str] = set()
    # Cold Work is default for mechanical work
    if work_type in ("corrective", "preventive", "predictive"):
        permits.add("PMT-CW")
    if asset_class in ("fired_heater", "flare"):
        permits.add("PMT-HW")
    if asset_class in ("column", "vessel"):
        permits.add("PMT-CS")
        permits.add("PMT-EI")
    if asset_class in ("electrical_motor", "transformer"):
        permits.add("PMT-EI")
    if asset_class in ("control_valve", "isolation_valve", "piping"):
        permits.add("PMT-LB")
        permits.add("PMT-EI")
    if work_type == "regulatory":
        permits.add("PMT-RA")
    return sorted(permits)


# ---------------------------------------------------------------------------
# Required crew skills by asset class
# ---------------------------------------------------------------------------

def required_skills_for(asset_class: str) -> list[str]:
    """Return a plausible list of required skill codes for a given asset class."""
    mapping: dict[str, list[str]] = {
        "centrifugal_pump":   ["mechanical", "rotating_equipment"],
        "reciprocating_pump": ["mechanical", "rotating_equipment"],
        "compressor":         ["mechanical", "rotating_equipment"],
        "heat_exchanger":     ["mechanical", "static_equipment"],
        "fired_heater":       ["mechanical", "static_equipment", "hot_work"],
        "column":             ["mechanical", "static_equipment", "confined_space"],
        "vessel":             ["mechanical", "static_equipment"],
        "control_valve":      ["mechanical", "instrumentation"],
        "isolation_valve":    ["mechanical"],
        "instrument":         ["instrumentation"],
        "piping":             ["mechanical", "welding"],
        "electrical_motor":   ["electrical", "mechanical"],
        "transformer":        ["electrical"],
        "cooling_tower":      ["mechanical", "static_equipment"],
        "flare":              ["mechanical", "hot_work"],
    }
    return mapping.get(asset_class, ["mechanical"])

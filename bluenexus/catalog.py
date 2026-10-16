"""Display names and candidate mappings. No inferred electrical rescaling."""
import re

SIGNALS = {
    "effluent_volume_m3": ("Product water", "m³/day", 1),
    "influent_volume_m3": ("Feed water", "m³/day", 1),
    "daily_electricity_kwh": ("Electricity", "kWh/day", 1),
    "expected_energy_kwh": ("Historical load estimate", "kWh/day", 1),
    "sec_kwh_m3": ("Energy per m³", "kWh/m³", 1),
    "planned_specific_energy_kwh_m3": ("Supplied energy target", "kWh/m³", 1),
    "sec_deviation": ("SEC versus plan", "%", 100),
    "energy_load_residual_fraction": ("Electricity versus load estimate", "%", 100),
    "peer_median_sec": ("Similar-output SEC reference", "kWh/m³", 1),
    "peer_gap_fraction": ("SEC versus similar-output reference", "%", 100),
    "peer_count": ("Earlier comparable days", "days", 1),
    "throughput_vs_supply_plan": ("Output versus supply plan", "%", 100),
    "recovery_calculated": ("Whole-plant volume recovery", "%", 100),
    "reported_recovery_rate": ("Reported plant recovery", "%", 100),
    "equipment_ro_recovery": ("Reported RO recovery", "%", 100),
    "recovery_cross_source_difference": ("Plant minus RO recovery", "percentage points", 100),
    "recovery_reporting_difference": ("Calculated minus reported recovery", "percentage points", 100),
    "reclaimed_supply_volume_m3": ("Reclaimed supply", "m³/day", 1),
    "customer_end_volume_m3": ("Customer-end volume", "m³/day", 1),
    "delivery_gap_m3": ("Supply minus customer volume", "m³/day", 1),
    "delivery_gap_fraction": ("Delivery discrepancy", "%", 100),
    "salt_passage_proxy": ("Product / feed conductivity", "%", 100),
    "effluent_ph": ("Product pH", "pH", 1),
    "influent_ph": ("Feed pH", "pH", 1),
    "influent_conductivity_us_cm": ("Feed conductivity", "µS/cm (reported)", 1),
    "effluent_conductivity_us_cm": ("Product conductivity", "µS/cm (reported)", 1),
    "actual_naoh_dose_reported": ("Recorded NaOH dose", "reported units (unverified)", 1),
    "planned_naoh_dose_reported": ("Planned NaOH dose", "reported units (unverified)", 1),
    "naoh_deviation": ("Recorded dose versus plan", "%", 100),
    "statistical_score": ("Statistical unusualness", "/100", 100),
    "pca_score": ("PCA unusualness", "/100", 100),
    "isolation_score": ("Isolation Forest unusualness", "/100", 100),
    "ensemble_score": ("Combined unusualness", "/100", 100),
}

def tag_info(tag):
    asset = "Plant / instrument"
    match = re.search(r"(?:^|zz_|p_)([12])_rohigh_pressure|ro([1-4])_high_pressure", tag)
    if match:
        asset = "RO pump " + next(x for x in match.groups() if x)
    kind, name, unit = "other", tag, "reported units (unverified)"
    if "qz_temp" in tag:
        kind, name, unit = "temperature", "QZ temperature (front bearing, provisional)", "°C assumed — verify scale"
    elif "hz_temp" in tag:
        kind, name, unit = "temperature", "HZ temperature (rear bearing, provisional)", "°C assumed — verify scale"
    elif tag.endswith("_wd") or "_tt_zjs_" in tag:
        kind, name, unit = "temperature", "Temperature (location unverified)", "°C assumed — verify scale"
    elif re.search(r"_[xyz](sd|wy)$", tag) or tag.endswith("_cz_o"):
        kind, name = "vibration", "Vibration " + (tag.rsplit("_", 1)[-1].upper())
    elif "tur_zcs" in tag:
        kind, name = "quality", "UF product turbidity"
    elif "frequency" in tag or tag.endswith(("fre_out", "fr_out")):
        kind, name, unit = "frequency", "Frequency", "Hz (reported)"
    elif "costheta" in tag:
        kind, name = "electrical", "Power-factor register (unscaled)"
    elif re.search(r"_i[abc]$", tag) or tag.endswith("_a_out") or "current_feedback" in tag:
        kind, name = "electrical", "Current register / feedback"
    elif re.search(r"_u[abc]$", tag):
        kind, name = "electrical", "Voltage register"
    elif "cumulative" in tag or tag.endswith("_ep") or tag.startswith("advancedtags"):
        kind, name = "counter", "Cumulative counter"
    elif tag in ("rohsl", "ufhsl"):
        kind, name, unit = "recovery", tag[:2].upper() + " reported recovery", "% (reported)"
    elif re.search(r"_(fault|output|rfb|run|start|stop)$", tag):
        kind, name = "state", "State / status register"
    return dict(signal=tag, asset=asset, label=name, unit=unit, kind=kind,
                confidence="Candidate tag meaning; asset location and scaling require verification")

def signal_info(key):
    if key in SIGNALS:
        return SIGNALS[key]
    info = tag_info(key)
    return info["label"], info["unit"], 1

PROCESS_RULES = {
    "RECOVERY_CORRIDOR": ("recovery", "Recovery outside review corridor", "recovery_calculated", "Outside 70–76% for 2 days; <65% or >85% immediately"),
    "RECOVERY_STEP_CHANGE": ("recovery", "Abrupt recovery change", "recovery_calculated", "Change >10 percentage points from preceding record"),
    "RECOVERY_SOURCE_DISAGREEMENT": ("data", "Plant and RO recovery sources disagree", "recovery_cross_source_difference", "Absolute difference >5 percentage points; different boundaries may explain it"),
    "RECOVERY_REPORT_MISMATCH": ("data", "Reported recovery does not match volumes", "recovery_reporting_difference", "Absolute difference >0.5 percentage points"),
    "DELIVERY_DISCREPANCY": ("delivery", "Supply and customer volumes disagree", "delivery_gap_fraction", "Absolute gap >10% for 2 days; >50% immediately"),
    "LOW_THROUGHPUT_ENERGY": ("energy", "High energy intensity at low output", "sec_kwh_m3", "SEC >20% above plan and output <40% of supply plan"),
    "ENERGY_ABOVE_PLAN": ("energy", "Energy intensity above plan", "sec_kwh_m3", "SEC >20% above plan for 2 consecutive days"),
    "ENERGY_LOAD_RESIDUAL": ("energy", "Electricity above the load estimate", "energy_load_residual_fraction", "Electricity >20% above prior fitted estimate for 2 days"),
    "NAOH_REPORTED_DEVIATION": ("quality", "Recorded NaOH dose differs from plan", "naoh_deviation", "Absolute recorded-dose deviation >30%; units unverified"),
    "EFFLUENT_PH": ("quality", "Product pH outside review interval", "effluent_ph", "Outside provisional pH 6.5–8.5; not a compliance limit"),
    "MULTIVARIATE_NOVELTY": ("data", "Unusual combination of process readings", "ensemble_score", "Score >85/100 with all 3 detectors for 2 days"),
}

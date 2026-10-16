"""One preparation path, prior-only comparisons, and a shared investigation schema."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import zipfile

import numpy as np
import pandas as pd
import polars as pl

from bluenexus.catalog import PROCESS_RULES, tag_info, signal_info
from bluenexus.detector import screen
from bluenexus.diagnostics.root_cause import diagnose_process
from bluenexus.features.feature_factory import build_features, build_equipment_features, feature_registry
from bluenexus.ingestion.sanitizer import ingest, FILES
from bluenexus.models.anomaly_ensemble import score_process, score_equipment
from bluenexus.settings import Settings

VERSION = "1.0.0"
CASE_COLUMNS = ["case_id", "plant", "code", "family", "priority", "asset", "signal", "title",
                "start", "end", "days", "value", "unit", "threshold", "confidence", "evidence", "rank"]
PRIORITIES = {"Verify promptly": 0, "Investigate": 1, "Check data": 2}

@dataclass
class Analysis:
    daily: pd.DataFrame
    equipment: pd.DataFrame
    cases: pd.DataFrame
    events: pd.DataFrame
    audit: pd.DataFrame
    quality: pd.DataFrame
    parsing: pd.DataFrame
    manifest: list
    training: list
    settings: dict
    fingerprint: str

def peers(frame, cfg):
    frame = frame.copy()
    frame["peer_count"] = 0
    frame["peer_median_sec"] = np.nan
    frame["peer_gap_fraction"] = np.nan
    frame["peer_dates"] = ""
    for plant, part in frame.groupby("plant"):
        for idx, row in part.iterrows():
            history = part.loc[(part.date < row.date) & (part.date >= row.date-pd.Timedelta(days=cfg.peer_lookback_days))]
            valid = history.loc[history.effluent_volume_m3.between(row.effluent_volume_m3*(1-cfg.peer_output_tolerance), row.effluent_volume_m3*(1+cfg.peer_output_tolerance)) & history.sec_kwh_m3.notna() & history.operating_state.ne("STANDBY_INDICATED")]
            frame.loc[idx, "peer_count"] = len(valid)
            frame.loc[idx, "peer_dates"] = ", ".join(valid.date.dt.strftime("%Y-%m-%d"))
            if len(valid) >= cfg.peer_minimum and pd.notna(row.sec_kwh_m3):
                baseline = valid.sec_kwh_m3.median()
                frame.loc[idx, "peer_median_sec"] = baseline
                if baseline > 0:
                    frame.loc[idx, "peer_gap_fraction"] = row.sec_kwh_m3/baseline-1
    return frame

def finite(value):
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    return None if value is None or isinstance(value, float) and not np.isfinite(value) else value

def event(plant, date, code, family, priority, asset, signal, title, value, threshold, evidence, confidence):
    return dict(plant=plant, date=pd.Timestamp(date), code=code, family=family, priority=priority,
                asset=asset, signal=signal, title=title, value=finite(value*signal_info(signal)[2] if value is not None else value), unit=signal_info(signal)[1],
                threshold=threshold, confidence=confidence, evidence={k: finite(v) for k, v in evidence.items()})

def equipment_events(equipment, cfg):
    result = []
    for plant, part in equipment.groupby("plant"):
        part = part.sort_values("date").set_index("date")
        for signal in part.select_dtypes("number"):
            info = tag_info(signal)
            values = part[signal]
            if values.notna().sum() == 0 or info["kind"] not in ("temperature", "vibration", "quality"):
                continue
            if info["kind"] == "temperature":
                for date, value in values[values > cfg.assumed_temperature_high].items():
                    result.append(event(plant,date,"TEMPERATURE_ASSUMED_HIGH","temperature","Verify promptly",info["asset"],signal,
                        "Temperature reading needs verification",value,f">{cfg.assumed_temperature_high:g} only if Celsius and scaling are confirmed",
                        {signal:value},"Celsius is assumed. Verify sensor identity and scaling before interpreting heating."))
            history = screen(values, cfg.equipment_baseline_days, cfg.equipment_iqr_multiplier).set_index("date")
            up = history.flag & history.value.gt(history.upper_fence)
            if info["kind"] == "temperature":
                up &= history.value.le(cfg.assumed_temperature_high)
            # A known zero speed suppresses load-dependent trend alerts, not absolute review.
            pump = info["asset"].split()[-1]
            frequency = f"{pump}_rohigh_pressure_pump_frequency_feedback_o" if plant == "Plant A" else f"c_m_ro{pump}_high_pressure_pump_fre_out"
            if frequency in part:
                up &= ~part[frequency].reindex(up.index).eq(0)
            streak = up.groupby((~up).cumsum()).cumsum()
            for date in up.index[up & streak.ge(cfg.equipment_persistence_days)]:
                value = history.loc[date,"value"]
                result.append(event(plant,date,"EQUIPMENT_PERSISTENT_RISE",info["kind"],"Investigate",info["asset"],signal,
                    info["label"] + " rising above history",value,
                    f"Above prior {cfg.equipment_baseline_days}-calendar-day Q3 + {cfg.equipment_iqr_multiplier}×IQR for {cfg.equipment_persistence_days} days",
                    {signal:value,"prior_upper_band":history.loc[date,"upper_fence"],"consecutive_days":int(streak.loc[date])},
                    "Relative change only; units, operating load and physical cause remain unverified."))
    return result

def group_cases(rows):
    if not rows:
        return pd.DataFrame(columns=CASE_COLUMNS), pd.DataFrame(columns=["case_id","date","plant","code","family","priority","asset","signal","title","value","unit","threshold","confidence","evidence"])
    events = pd.DataFrame(rows).sort_values(["plant","code","signal","date"]).reset_index(drop=True)
    events["case_id"] = ""
    cases = []
    for keys, group in events.groupby(["plant","code","signal"],sort=False):
        blocks = group.date.diff().ne(pd.Timedelta(days=1)).cumsum()
        for _, episode in group.groupby(blocks):
            first, last = episode.iloc[0], episode.iloc[-1]
            identifier = sha256(("|".join(keys)+"|"+first.date.isoformat()).encode()).hexdigest()[:16]
            priority = min(episode.priority, key=lambda p: PRIORITIES[p])
            record = last.drop(labels=["date", "case_id"]).to_dict()
            record.update(case_id=identifier, start=first.date, end=last.date, days=len(episode), priority=priority, rank=PRIORITIES[priority])
            cases.append(record)
            events.loc[episode.index,"case_id"] = identifier
    return pd.DataFrame(cases)[CASE_COLUMNS].sort_values(["rank","end","plant"],ascending=[True,False,True]).reset_index(drop=True), events

def analyze(blobs, cfg=Settings()):
    data = ingest(Path("data/raw"), cfg, blobs)
    model = score_process(build_features(data),cfg)
    daily = peers(model.scored.to_pandas(),cfg)
    equipment = data.raw_equipment.to_pandas()
    equipment["date"] = pd.to_datetime(equipment.date)
    rows = []
    for row in diagnose_process(model.scored,cfg).iter_rows(named=True):
        family, title, signal, threshold = PROCESS_RULES[row["code"]]
        evidence = json.loads(row["evidence"])
        if family == "energy":
            context = daily.loc[daily.plant.eq(row["plant"]) & daily.date.eq(pd.Timestamp(row["date"]))].iloc[0]
            for key in ["daily_electricity_kwh","effluent_volume_m3","sec_kwh_m3","planned_specific_energy_kwh_m3","expected_energy_kwh","energy_load_residual_fraction","peer_count","peer_median_sec","peer_gap_fraction"]:
                evidence[key] = finite(context[key])
        priority = "Verify promptly" if row["severity"] == "critical" else "Check data" if family == "data" else "Investigate"
        asset = "Delivery meters / storage" if family == "delivery" else "Product sampling / dosing" if family == "quality" else "Whole plant"
        rows.append(event(row["plant"],row["date"],row["code"],family,priority,asset,signal,title,evidence.get(signal),threshold,evidence,
                          "Calculated from daily records; site limits, measurement boundaries and cause require verification."))
    # Add a matched-output rule once, alongside the distinct plan and load-model rules.
    for _, row in daily.loc[daily.peer_gap_fraction.gt(cfg.energy_deviation)].iterrows():
        rows.append(event(row.plant,row.date,"ENERGY_PEER","energy","Investigate","Whole plant","peer_gap_fraction",
                    "Energy intensity above similar-output days",row.peer_gap_fraction,
                    f">{cfg.energy_deviation:.0%} above median of ≥{cfg.peer_minimum} earlier days within ±{cfg.peer_output_tolerance:.0%} output",
                    {c:row[c] for c in ["sec_kwh_m3","peer_count","peer_median_sec","peer_gap_fraction","energy_load_residual_fraction"]},
                    "Output-matched comparison; runtime, cleaning and feed conditions are not controlled."))
    rows.extend(equipment_events(equipment,cfg))
    for item in data.quality_events.filter(pl.col("code").is_in(["PHYSICAL_RANGE","COUNTER_DECREASE"])).iter_rows(named=True):
        info = tag_info(item["signal"])
        title = "Counter decreased" if item["code"] == "COUNTER_DECREASE" else "Reading outside application range"
        rows.append(event(item["plant"],item["date"],item["code"],"data","Check data",info["asset"],item["signal"],title,item["raw_value"],
                    item["message"],{item["signal"]:item["raw_value"]},"Data review; this does not establish equipment failure."))
    cases, events = group_cases(rows)
    signature = sha256(json.dumps([VERSION,data.source_manifest,cfg.to_dict()],sort_keys=True).encode()).hexdigest()
    return Analysis(daily,equipment,cases,events,data.column_audit.to_pandas(),data.quality_events.to_pandas(),
                    pd.DataFrame(data.parsing_log),data.source_manifest,model.training_runs,cfg.to_dict(),signature)

def in_scope(frame, plant, start, end, episodes=False):
    selected = frame if plant == "All plants" else frame.loc[frame.plant.eq(plant)]
    start,end = pd.Timestamp(start),pd.Timestamp(end)
    mask = selected.start.le(end) & selected.end.ge(start) if episodes else selected.date.between(start,end)
    return selected.loc[mask].copy()

def energy_summary(frame):
    valid = frame.loc[frame.sec_kwh_m3.notna()]
    planned = valid.loc[valid.planned_specific_energy_kwh_m3.gt(0)]
    gap = planned.daily_electricity_kwh-planned.effluent_volume_m3*planned.planned_specific_energy_kwh_m3
    return dict(water=frame.effluent_volume_m3.sum(min_count=1), energy=frame.daily_electricity_kwh.sum(min_count=1),
                sec=valid.daily_electricity_kwh.sum()/valid.effluent_volume_m3.sum() if len(valid) else np.nan,
                days=len(valid),net=gap.sum(min_count=1),positive=gap.clip(lower=0).sum(min_count=1))

def analysis_bundle(result):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as archive:
        for name, frame in [("daily_comparisons",result.daily),("investigations",result.cases),("daily_rule_evidence",result.events),
                            ("channel_audit",result.audit),("quality_events",result.quality),("parsing_log",result.parsing)]:
            export = frame.copy()
            if "evidence" in export:
                export["evidence"] = export.evidence.map(lambda x: json.dumps(x,default=str,allow_nan=False))
            archive.writestr(name+".csv",export.to_csv(index=False))
        for name,value in [("manifest",result.manifest),("settings",result.settings),("training_runs",result.training),("feature_registry",feature_registry())]:
            archive.writestr(name+".json",json.dumps(value,indent=2,default=str))
        archive.writestr("version.json",json.dumps(dict(version=VERSION,fingerprint=result.fingerprint)))
    return buffer.getvalue()

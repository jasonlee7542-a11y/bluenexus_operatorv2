from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bluenexus.service import analyze,peers,event,group_cases,in_scope,analysis_bundle
from bluenexus.settings import Settings
from bluenexus.ingestion.sanitizer import FILES,parse_frame
from bluenexus.workflow import recommendation,worklog_payload,import_worklog,CURRENT,OUTCOMES

@pytest.fixture(scope="module")
def result():
    if not all((ROOT/"data/raw"/f).exists() for f in FILES):
        pytest.skip("Restricted challenge CSVs not present")
    return analyze({f:(ROOT/"data/raw"/f).read_bytes() for f in FILES})

def test_real_energy_example_keeps_three_comparisons_distinct(result):
    row=result.daily.loc[result.daily.plant.eq("Plant A")&result.daily.date.eq("2026-08-31")].iloc[0]
    assert row.sec_kwh_m3==pytest.approx(3660/1881)
    assert row.sec_deviation==pytest.approx(.621477937,rel=1e-6)
    assert .08 < row.energy_load_residual_fraction < .11
    assert row.peer_count==2 and pd.isna(row.peer_gap_fraction)

def test_extreme_constant_temperature_is_not_lost_to_relative_baseline(result):
    rows=result.cases.loc[result.cases.code.eq("TEMPERATURE_ASSUMED_HIGH")&result.cases.plant.eq("Plant A")]
    assert len(rows)==1
    row=rows.iloc[0]
    assert row.days==27 and row.start==pd.Timestamp("2026-01-01") and row.end==pd.Timestamp("2026-01-27")
    assert "assumed" in row.unit and row.value>212

def test_delivery_arithmetic_and_export_units(result):
    row=result.cases.loc[result.cases.code.eq("DELIVERY_DISCREPANCY")].iloc[0]
    assert row.evidence["delivery_gap_m3"]==20214
    assert row.value==pytest.approx(20214/21187*100)
    assert row.unit=="%"
    assert row.priority=="Verify promptly"

def test_peer_reference_ignores_future_and_current_observations():
    cfg=Settings(peer_minimum=3)
    frame=pd.DataFrame(dict(plant=["Plant A"]*8,date=pd.date_range("2026-01-01",periods=8),
        effluent_volume_m3=[100]*8,sec_kwh_m3=[1,1,1,1,1,1,1,20],operating_state=["ACTIVE_INDICATED"]*8))
    original=peers(frame,cfg)
    prefix=peers(frame.iloc[:7],cfg)
    assert original.iloc[:7].peer_median_sec.equals(prefix.peer_median_sec)
    assert original.iloc[-1].peer_median_sec==1

def test_grouping_breaks_on_calendar_gap_and_preserves_escalation():
    rows=[]
    for date,priority in [("2026-01-01","Investigate"),("2026-01-02","Verify promptly"),("2026-01-04","Investigate")]:
        rows.append(event("Plant A",date,"X","energy",priority,"Whole plant","sec_kwh_m3","Example",2,"test",{"sec_kwh_m3":2},"test"))
    cases,events=group_cases(rows)
    assert len(cases)==2 and len(events)==3
    first=cases.loc[cases.start.eq("2026-01-01")].iloc[0]
    assert first.days==2 and first.priority=="Verify promptly"
    scoped=in_scope(cases,"Plant A","2026-01-02","2026-01-02",episodes=True)
    assert len(scoped)==1

def test_empty_rule_result_has_a_usable_schema():
    cases,events=group_cases([])
    assert {"plant","signal","date","value"} <= set(events)
    assert in_scope(cases,"All plants","2026-01-01","2026-01-31",episodes=True).empty

def test_route_requires_current_evidence_before_recommendation():
    case={"priority":"Verify promptly","family":"temperature"}
    assert recommendation(case,{})[0]=="Verify current condition"
    assert recommendation(case,{"current":CURRENT[1]})[0]=="Record verification evidence"
    review=dict(current=CURRENT[1],outcome=OUTCOMES[1],evidence="Independent reading and timestamp")
    assert recommendation(case,review)[0]=="Contact site / engineering"
    review["current"]=CURRENT[2]
    assert recommendation(case,review)[0]=="Historical follow-up"

def test_worklog_restore_rejects_cross_dataset_and_bad_enums():
    records={"abc":dict(current=CURRENT[1],outcome=OUTCOMES[1],evidence="Reading")}
    payload=worklog_payload(records,"fingerprint")
    assert import_worklog(payload,"fingerprint",{"abc"})==records
    with pytest.raises(ValueError): import_worklog(payload,"different",{"abc"})
    with pytest.raises(ValueError): import_worklog(payload,"fingerprint",{"other"})
    records["abc"]["current"]="invented"
    with pytest.raises(ValueError): import_worklog(worklog_payload(records,"fingerprint"),"fingerprint",{"abc"})

def test_bundle_is_reproducible_evidence_and_raw_sources_remain_unchanged(result):
    import hashlib,zipfile,io
    archive=zipfile.ZipFile(io.BytesIO(analysis_bundle(result)))
    assert {"daily_comparisons.csv","investigations.csv","settings.json","manifest.json"} <= set(archive.namelist())
    for item in result.manifest:
        assert hashlib.sha256((ROOT/"data/raw"/item["file"]).read_bytes()).hexdigest()==item["sha256"]

def test_future_append_does_not_change_past_cases(result):
    blobs={}
    for f in FILES:
        source=pd.read_csv(ROOT/"data/raw"/f)
        source=source.loc[pd.to_datetime(source.date)<=pd.Timestamp("2026-08-20")]
        blobs[f]=source.to_csv(index=False).encode()
    short=analyze(blobs)
    before=result.events.loc[result.events.date<=pd.Timestamp("2026-08-20")]
    keys=["plant","date","code","signal","priority"]
    pd.testing.assert_frame_equal(before[keys].sort_values(keys).reset_index(drop=True),short.events[keys].sort_values(keys).reset_index(drop=True))

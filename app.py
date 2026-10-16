"""BlueNexus Operations Review. Streamlit entry point: app.py."""
from pathlib import Path
from io import BytesIO
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from bluenexus.catalog import PROCESS_RULES, SIGNALS, signal_info, tag_info
from bluenexus.charts import lines,style,display,equipment_chart,NAVY,BLUE,AMBER
from bluenexus.detector import screen
from bluenexus.ingestion.sanitizer import FILES
from bluenexus.playbooks import playbook
from bluenexus.service import VERSION,analyze,in_scope,energy_summary,analysis_bundle
from bluenexus.workflow import CURRENT,OUTCOMES,recommendation,handoff,worklog_payload,import_worklog,timestamp

st.set_page_config(page_title="BlueNexus | Operations review",page_icon=":material/water_drop:",layout="wide")
st.html(ROOT/"assets/dashboard.css")
VIEWS=["Operations","Investigations","Energy","Water & quality","Equipment","Data & methods"]
for key,value in dict(view="Operations",plant="All plants",period="Performance period",reviews={},revision=0).items():
    st.session_state.setdefault(key,value)

def navigate(view,plant=None,case_id=None,period=None):
    st.session_state.view=view
    if plant: st.session_state.plant=plant
    if period: st.session_state.period=period
    if case_id:
        st.session_state.focus_case=case_id
        st.session_state.case_type="All cases"
        st.session_state.case_priority=["Verify promptly","Investigate","Check data"]

def show_equipment_history(plant,signal):
    navigate("Equipment",plant,period="All equipment history")
    st.session_state["equipment_"+plant]=signal

def toggle_case_queue():
    st.session_state.show_all_cases=not st.session_state.get("show_all_cases",False)

@st.cache_data(show_spinner=False,max_entries=4)
def prepare(blobs,version):
    return analyze(blobs)

def plot(fig,key=None):
    st.plotly_chart(fig,width="stretch",theme=None,key=key,config={"displaylogo":False,"scrollZoom":False})

def evidence_table(evidence,case=None):
    rows=[]
    for key,value in evidence.items():
        label,unit,scale=signal_info(key)
        if key=="prior_upper_band" and case is not None: label,unit="Prior upper statistical band",case.unit
        if key=="consecutive_days": label,unit="Consecutive upward deviations","days"
        rows.append({"Measurement":label,"Reading":display(value*scale if isinstance(value,(int,float)) else value,3),"Unit":unit})
    return pd.DataFrame(rows)

def queue_table(cases):
    table=cases[["priority","plant","title","days"]].copy()
    table["Flagged period"]=cases.start.dt.strftime("%d %b")+" – "+cases.end.dt.strftime("%d %b %Y")
    return table.rename(columns={"priority":"Priority","plant":"Plant","title":"Investigation","days":"Days"})[["Priority","Plant","Investigation","Flagged period","Days"]]

def badge(priority):
    st.badge(priority,icon=":material/priority_high:" if priority=="Verify promptly" else ":material/search:",color="red" if priority=="Verify promptly" else "orange" if priority=="Investigate" else "blue")

with st.sidebar:
    with st.container(key="brand"):
        st.image(str(ROOT/"assets/bluenexus-logo.png"),width=170)
    st.caption("OPERATIONS REVIEW")
    st.selectbox("Plant",["All plants","Plant A","Plant B"],key="plant")
    st.selectbox("Review period",["Performance period","All equipment history","Latest 30 recorded days","Custom dates"],key="period")
    with st.expander("Data inputs"):
        st.caption("Upload all three files to replace the local dataset for this session.")
        uploaded=st.file_uploader("Challenge CSVs",type="csv",accept_multiple_files=True,key="source_uploads")
        st.caption("Expected filenames: "+", ".join(FILES))
    st.badge("Historical data",icon=":material/history:",color="blue")

blobs={}
if uploaded:
    names=[f.name for f in uploaded]
    if len(names)!=len(set(names)) or set(names)!=set(FILES):
        st.title("Load the challenge data")
        st.info("Upload exactly the three expected CSV files together. Partial uploads are not mixed with another dataset.")
        st.stop()
    blobs={f.name:f.getvalue() for f in uploaded}
else:
    blobs={name:(ROOT/"data/raw"/name).read_bytes() for name in FILES if (ROOT/"data/raw"/name).is_file()}
if set(blobs)!=set(FILES):
    st.title("BlueNexus operations review")
    st.write("Load the three challenge CSVs using **Data inputs** in the sidebar to begin.")
    st.info("The GitHub package contains the application. Your plant dataset is loaded separately.")
    st.caption("For local use, place the files in data/raw/. See README.md for deployment instructions.")
    st.stop()
try:
    with st.spinner("Preparing evidence and historical comparisons…"):
        result=prepare(blobs,VERSION)
except Exception as exc:
    st.error(f"Unable to prepare the supplied data: {exc}")
    st.info("Check filenames, plant/date keys and the required columns. Original files have not been changed.")
    st.stop()

if st.session_state.get("analysis_id")!=result.fingerprint:
    st.session_state.analysis_id=result.fingerprint
    st.session_state.reviews={}
    st.session_state.revision+=1
    st.session_state.pop("focus_case",None)

plant=st.session_state.plant
plants=["Plant A","Plant B"] if plant=="All plants" else [plant]
first=result.equipment.date.min().date(); last=result.equipment.date.max().date()
performance_start=result.daily.date.min().date();performance_end=result.daily.date.max().date()
if st.session_state.period=="Performance period": start,end=performance_start,performance_end
elif st.session_state.period=="All equipment history": start,end=first,last
elif st.session_state.period=="Latest 30 recorded days": start,end=(pd.Timestamp(last)-pd.Timedelta(days=29)).date(),last
else:
    dates=st.sidebar.date_input("Date interval",value=(performance_start,performance_end),min_value=min(first,performance_start),max_value=max(last,performance_end),key="dates")
    if len(dates)!=2:
        st.info("Choose both the start and end date.");st.stop()
    start,end=dates
if start>end:
    st.error("Start date must be on or before end date.");st.stop()
with st.sidebar:
    st.caption(f"{start:%d %b %Y} — {end:%d %b %Y}")
    st.button("Reset review scope",on_click=navigate,args=("Operations","All plants",None,"Performance period"),width="stretch")
    st.divider()
    st.caption(f"{len(st.session_state.reviews)} saved reviews · export to retain")
    st.download_button("Export work log",worklog_payload(st.session_state.reviews,result.fingerprint),"BlueNexus_work_log.json","application/json",width="stretch")

daily=in_scope(result.daily,plant,start,end)
equipment=in_scope(result.equipment,plant,start,end)
cases=in_scope(result.cases,plant,start,end,episodes=True)
st.segmented_control("Workspace",VIEWS,key="view",selection_mode="single",width="stretch",label_visibility="collapsed")
view=st.session_state.view or "Operations"
st.title(view)
st.caption(f"{plant}   /   {start:%d %b} – {end:%d %b %Y}   /   Historical review")

# Keep excluded priority evidence visible wherever an operator enters the app.
outside=result.cases.loc[result.cases.plant.isin(plants)&result.cases.priority.eq("Verify promptly")&~result.cases.case_id.isin(cases.case_id)]
def priority_history():
    st.caption("Outside the selected date range · historical flags, not current alarms")
    for row in outside.loc[outside.code.eq("TEMPERATURE_ASSUMED_HIGH")].itertuples():
        readings=result.equipment.loc[result.equipment.plant.eq(row.plant)&result.equipment.date.between(row.start,row.end),row.signal]
        st.metric(f"{row.plant} · {row.asset} · QZ temperature" if "qz_temp" in row.signal else f"{row.plant} · {row.asset} · Temperature",f"{readings.max():.1f}",help="Original reported value. Celsius and scaling require confirmation.")
        st.caption(f"{row.start:%d %b}–{row.end:%d %b %Y} · {row.days} days · Unit unverified")
        month=row.start.strftime("%B") if row.start.month==row.end.month else "flagged"
        st.button(f"View {month} readings · {row.plant}",on_click=show_equipment_history,args=(row.plant,row.signal),key="history_"+row.case_id)
    if len(outside.loc[~outside.code.eq("TEMPERATURE_ASSUMED_HIGH")]):
        st.dataframe(queue_table(outside),hide_index=True,width="stretch")
        st.button("Review flagged episodes",on_click=navigate,args=("Investigations",plant,outside.iloc[0].case_id,"All equipment history"))
    st.caption("Resolution unknown · no repair confirmation in this dataset")

if len(outside):
    first_hidden=outside.iloc[0]
    hidden_label=f"Flagged readings outside these dates · {first_hidden.plant} · {first_hidden.start:%b %Y}"
    if first_hidden.code=="TEMPERATURE_ASSUMED_HIGH":
        hidden_label+=f" · temperature {first_hidden.value:.1f} (unit unverified)"
    if len(outside)>1: hidden_label+=f" · +{len(outside)-1} more"
    with st.expander(":material/history: "+hidden_label):
        priority_history()

if view=="Operations":
    st.subheader("Production snapshot")
    for col,name in zip(st.columns(len(plants)),plants):
        part=daily.loc[daily.plant.eq(name)]; s=energy_summary(part)
        with col,st.container(key="panel_plant_"+name):
            st.markdown(f"**:material/water_drop: {name}**")
            a,b=st.columns(2)
            a.metric("Product water · m³",display(s["water"],0),help="Total product water over the selected dates on matching valid energy/water records.")
            b.metric("Energy · kWh/m³",display(s["sec"],3),help="Total electricity ÷ product water on matching valid dates.")
            if not part.empty:
                fig=lines(part,["effluent_volume_m3"]);fig.update_layout(height=180,showlegend=False,margin=dict(l=10,r=10,t=10,b=10))
                plot(fig,key="snapshot_"+name)
            else: st.caption("No performance records in this scope.")
    st.subheader("Investigations in selected dates")
    c1,c2,c3=st.columns(3)
    with c1,st.container(key="kpi_priority"):
        st.metric("Verify promptly",str(cases.priority.eq("Verify promptly").sum()),help="Historical episodes in the selected dates. Not live or unresolved alarms.")
        st.caption(":material/priority_high: Priority checks")
    with c2,st.container(key="kpi_investigate"):
        st.metric("Process & equipment",str(cases.family.ne("data").sum()),help="Historical episodes; may overlap priority checks.")
        st.caption(":material/troubleshoot: Investigation queue")
    with c3,st.container(key="kpi_data"):
        st.metric("Data checks",str(cases.family.eq("data").sum()),help="Historical consistency episodes, not confirmed faults.")
        st.caption(":material/fact_check: Measurement confidence")
    main=cases.loc[cases.family.ne("data")]
    focus=st.container()
    with focus:
        st.subheader("Next investigation")
    if len(main):
        top=main.iloc[0]
        with focus,st.container(key="next_action"):
            left,right=st.columns([3,1],vertical_alignment="center")
            with left:
                badge(top.priority)
                st.subheader(top.title)
                st.write(f"**{top.plant} · {top.asset}** · {top.start:%d %b}–{top.end:%d %b %Y}")
                with st.expander("First check"):
                    st.write(playbook(top.family,top.asset)["remote"][0])
            with right:
                st.button("Open investigation",type="primary",on_click=navigate,args=("Investigations",top.plant,top.case_id),width="stretch")
    else:
        st.info("No process/equipment rule episodes intersect these dates. Check available channels and data issues before drawing a health conclusion.")
        st.button("Review data cases",on_click=navigate,args=("Investigations",))
    expanded=st.session_state.get("show_all_cases",False)
    if len(cases):
        with focus:
            if not expanded:
                preview=main.head(4) if len(main) else cases.head(4)
                st.dataframe(queue_table(preview),hide_index=True,width="stretch",key="case_preview")
            st.button("Show fewer cases" if expanded else f"Browse all {len(cases)} cases",on_click=toggle_case_queue,key="browse")
        if expanded:
            st.subheader(f"All {len(cases)} investigations")
            st.caption("Selected plant and dates · includes data checks")
            st.dataframe(queue_table(cases),hide_index=True,width="stretch",height=35*(len(cases)+1)+3,row_height=35,key="case_full_queue",column_config={"Investigation":st.column_config.TextColumn(width="large"),"Days":st.column_config.NumberColumn(width="small")})
    with st.expander("Guided walkthrough · three decisions"):
        st.caption("Each shortcut opens historical evidence. Current-condition answers remain yours to verify.")
        for name,which,code,date in [("Why high SEC does not automatically justify a visit","Plant A","LOW_THROUGHPUT_ENERGY","2026-08-31"),("Reconcile a large delivery discrepancy","Plant B","DELIVERY_DISCREPANCY","2026-08-11"),("Verify an extreme temperature reading","Plant A","TEMPERATURE_ASSUMED_HIGH","2026-01-01")]:
            found=result.cases.loc[result.cases.plant.eq(which)&result.cases.code.eq(code)&result.cases.start.le(pd.Timestamp(date))&result.cases.end.ge(pd.Timestamp(date))]
            if len(found): st.button(name,on_click=navigate,args=("Investigations",which,found.iloc[0].case_id,"All equipment history"),key="story_"+code)

elif view=="Investigations":
    st.session_state.setdefault("case_priority",["Verify promptly","Investigate","Check data"])
    with st.expander("Filter the investigation queue"):
        family=st.selectbox("Case type",["All cases","Process & equipment","Data consistency"],key="case_type")
        priority=st.multiselect("Review priority",["Verify promptly","Investigate","Check data"],key="case_priority")
    available=cases.loc[cases.priority.isin(priority)]
    if family=="Process & equipment": available=available.loc[available.family.ne("data")]
    elif family=="Data consistency": available=available.loc[available.family.eq("data")]
    focus=st.session_state.pop("focus_case",None)
    if focus and focus not in available.case_id.values and focus in cases.case_id.values:
        available=cases
        st.caption("Showing all case types for the linked investigation. Adjust filters to resume a filtered queue.")
    if available.empty:
        st.info("No cases match this scope and these filters. This does not establish healthy operation.");st.stop()
    options=available.case_id.tolist()
    if focus in options: st.session_state.selected_case=focus
    if st.session_state.get("selected_case") not in options: st.session_state.selected_case=options[0]
    selected=st.selectbox("Investigation",options,
                          format_func=lambda x: f"{available.loc[available.case_id.eq(x)].iloc[0].priority} · {available.loc[available.case_id.eq(x)].iloc[0].plant} · {available.loc[available.case_id.eq(x)].iloc[0].start:%d %b %Y} · {available.loc[available.case_id.eq(x)].iloc[0].title}",
                          key="selected_case")
    row=available.loc[available.case_id.eq(selected)].iloc[0]
    book=playbook(row.family,row.asset)
    review=st.session_state.reviews.get(selected,{})
    action,reason=recommendation(row,review)
    badge(row.priority)
    st.subheader(row.title)
    st.caption(f"{row.plant} · {row.asset} (candidate mapping) · {row.start:%d %b}–{row.end:%d %b %Y} · {row.days} qualifying day(s)")
    with st.container(key="next_action"):
        st.markdown(f"**Next action: {action}**")
        with st.expander("Decision logic"):
            st.write(reason)
    left,right=st.columns([1.35,1],gap="large")
    with left:
        a,b=st.columns(2)
        a.metric("Last qualifying reading",display(row.value,2),help=row.unit)
        b.metric("Qualifying days",str(row.days))
        st.caption(row.unit)
        with st.expander("Evidence & threshold"):
            st.write(row.threshold)
            st.table(evidence_table(row.evidence,row))
            st.caption(f"Last qualifying day: {row.end:%d %b %Y}. {row.confidence}")
        if row.family=="energy":
            matched=result.daily.loc[result.daily.plant.eq(row.plant)&result.daily.date.eq(row.end)]
            if len(matched):
                e=matched.iloc[0]
                if pd.notna(e.energy_load_residual_fraction):
                    st.info(f"Production-adjusted view: electricity was {e.energy_load_residual_fraction:+.1%} versus the historical load estimate. The provisional excess-energy threshold is +20%.")
                if pd.isna(e.peer_gap_fraction):
                    st.caption(f"Similar-output comparison unavailable: {int(e.peer_count)} earlier peers; at least 5 required. An unavailable comparison is not a healthy result.")
        origin=result.equipment if row.signal in result.equipment else result.daily
        context=origin.loc[origin.plant.eq(row.plant)&origin.date.between(row.start-pd.Timedelta(days=14),row.end+pd.Timedelta(days=7))]
        if row.signal in context and context[row.signal].notna().any():
            fig=lines(context,[row.signal])
            fig.add_vrect(x0=row.start,x1=row.end+pd.Timedelta(days=1),fillcolor=AMBER,opacity=.10,line_width=0,layer="below")
            plot(fig)
            st.caption("Shaded: flagged episode · includes surrounding dates · not a repair timeline")
    with right:
        st.markdown("**Remote checks · start here**")
        st.info(book["remote"][0],icon=":material/search:")
        with st.expander("Remaining checks"):
            for i,step in enumerate(book["remote"][1:],2): st.write(f"{i}. {step}")
        with st.expander("Possible causes & missing evidence"):
            for cause in book["causes"]: st.write("• "+cause)
            st.caption("These are hypotheses, not diagnoses.")
            st.write("**Still needed:** "+book["missing"])
    t1,t2,t3=st.tabs(["Record verification","Technician handoff","Daily evidence"])
    with t1:
        st.caption("Save before leaving · export work log to retain")
        with st.form("review_"+selected+"_"+str(st.session_state.revision)):
            l,r=st.columns(2)
            current=l.selectbox("Current condition",CURRENT,index=CURRENT.index(review.get("current",CURRENT[0])))
            outcome=r.selectbox("Remote investigation result",OUTCOMES,index=OUTCOMES.index(review.get("outcome",OUTCOMES[0])))
            evidence=st.text_area("Verification evidence · reading, timestamp and source",value=review.get("evidence",""),placeholder="Record the current measurement and when/how it was checked. Historical CSV values do not confirm a current condition.")
            l,r=st.columns(2)
            owner=l.text_input("Review owner",value=review.get("owner",""))
            asset=r.text_input("Confirmed physical asset / tag",value=review.get("asset",""))
            followup=st.text_input("Follow-up time and responsible team",value=review.get("followup",""))
            notes=st.text_area("Findings and completed checks",value=review.get("notes",""))
            saved=st.form_submit_button("Save verification and update recommendation",type="primary")
        if saved:
            st.session_state.reviews[selected]=dict(current=current,outcome=outcome,evidence=evidence,owner=owner,asset=asset,followup=followup,notes=notes,updated_at=timestamp())
            st.rerun()
        if review: st.caption("Last saved: "+review.get("updated_at","")+" · Operator entered; not independently verified by this app.")
    with t2:
        st.markdown("**Where the technician should start**")
        st.write(book["location"])
        for i,step in enumerate(book["site"],1): st.write(f"{i}. {step}")
        st.write("**Attendance condition:** "+book["trigger"])
        if not all(review.get(k,"").strip() for k in ["owner","asset","evidence","followup"]):
            st.warning("Handoff is a draft: confirm the owner, physical asset, verification evidence and follow-up before assigning work.")
        st.download_button("Download investigation handoff",handoff(row,review,result),f"BlueNexus_{selected}_handoff.md","text/markdown",type="primary")
        st.caption("This prepares a document. It does not dispatch a technician or issue control commands.")
    with t3:
        detail=result.events.loc[result.events.case_id.eq(selected)].copy()
        detail.evidence=detail.evidence.map(lambda x:json.dumps(x,default=str,ensure_ascii=False))
        st.dataframe(detail[["date","value","unit","priority","evidence"]],hide_index=True,width="stretch")
        st.code(row.signal,language=None)
        st.download_button("Download daily rule evidence",detail.to_csv(index=False).encode(),f"{selected}_evidence.csv","text/csv")

elif view=="Energy":
    if daily.empty: st.info("No performance records in these dates. Select the performance period.")
    for name in plants:
        part=daily.loc[daily.plant.eq(name)]
        if part.empty: continue
        st.subheader(name)
        s=energy_summary(part);a,b,c=st.columns(3)
        a.metric("Energy · kWh/m³",display(s["sec"],3),border=True,help="Weighted: electricity ÷ product water on matching valid dates.")
        b.metric("Days >20% above estimate",str(part.energy_load_residual_fraction.gt(.2).sum()),border=True,help="Descriptive count. An investigation requires two consecutive days.")
        c.metric("Peer coverage",f"{part.peer_gap_fraction.notna().sum()}/{len(part)}",border=True,help="Days with enough earlier similar-output comparisons. Missing days are unassessed.")
        intensity,load=st.tabs(["Energy per m³","Production-adjusted energy"])
        with intensity:
            plot(lines(part,["sec_kwh_m3","planned_specific_energy_kwh_m3","peer_median_sec"]),key="sec_"+name)
            st.caption("Solid: actual · dotted: supplied target / earlier similar-output reference")
        with load:
            plot(lines(part,["daily_electricity_kwh","expected_energy_kwh"]),key="load_"+name)
            residual=lines(part,["energy_load_residual_fraction"],"Electricity versus estimate · %")
            residual.add_hline(y=20,line_dash="dash",line_color=AMBER,annotation_text="Review +20%")
            residual.add_hline(y=0,line_color="#acbdc9")
            plot(residual,key="residual_"+name)
            st.caption(f"Estimate coverage: {part.expected_energy_kwh.notna().sum()}/{len(part)} days · earlier observations only")
        with st.expander("Daily evidence & target definitions"):
            st.write("Supplied target = reference from the challenge CSV. Historical estimate = fitted from earlier output and energy. Neither establishes a fault; output adjustment does not account for feedwater, cleaning or runtime.")
            a,b=st.columns(2);a.metric("Net energy versus target",display(s["net"],0)+" kWh");b.metric("Above-target days only",display(s["positive"],0)+" kWh")
            st.caption("These are reference gaps, not demonstrated or attainable savings.")
            st.dataframe(part[["date","effluent_volume_m3","daily_electricity_kwh","sec_kwh_m3","expected_energy_kwh","energy_load_residual_fraction","peer_count","peer_gap_fraction","peer_dates"]],hide_index=True,width="stretch")
        st.button("Review "+name+" investigations",on_click=navigate,args=("Investigations",name),key="energy_cases_"+name)
    with st.expander("How the two comparisons work"):
        st.write("Similar-output reference: median SEC on at least five earlier, non-standby-indicated days within ±20% of output over the prior 60 days. Load model: nonnegative fixed electricity plus a nonnegative production-dependent term, fitted on at least 14 earlier eligible observations and refreshed every seven rows. Neither comparison establishes a cause.")

elif view=="Water & quality":
    if daily.empty: st.info("No performance records in these dates.")
    for name in plants:
        part=daily.loc[daily.plant.eq(name)]
        if part.empty: continue
        st.subheader(name)
        if name=="Plant A":
            st.metric("Reported volume recovery",display(part.recovery_calculated.median()*100,1)+"%",border=True,help="Fixed reported volume ratio; not independent evidence of membrane health.")
        else:
            plot(lines(part,["recovery_calculated","equipment_ro_recovery"],"Recovery · %"),key="recovery_"+name)
        st.markdown("**Supply and customer volumes**")
        plot(lines(part,["reclaimed_supply_volume_m3","customer_end_volume_m3"]),key="delivery_"+name)
        valid=part.delivery_gap_fraction.dropna()
        if len(valid):
            worst=part.loc[valid.abs().idxmax()]
            st.caption(f"Largest absolute discrepancy: {abs(worst.delivery_gap_fraction):.1%} on {worst.date:%d %b %Y}; signed gap {worst.delivery_gap_m3:,.0f} m³. Reconcile time, storage and branches before interpreting loss.")
        left,right=st.columns(2)
        with left:
            st.markdown("**Product pH**")
            fig=lines(part,["effluent_ph"]);fig.add_hrect(y0=6.5,y1=8.5,fillcolor=BLUE,opacity=.07,line_width=0,layer="below");plot(fig,key="ph_"+name)
        with right:
            st.markdown("**Conductivity passage proxy**")
            plot(lines(part,["salt_passage_proxy"]),key="conductivity_"+name)
        with st.expander("How to interpret water & quality"):
            st.write("Recovery measurements may have different boundaries. Plant A's fixed 75% ratio does not establish membrane health. pH shading is a provisional review interval, not a compliance limit. Conductivity is a proxy; sample locations need confirmation.")
        with st.expander("Chemical records and reporting coverage"):
            st.write(f"NaOH recorded on {part.actual_naoh_dose_reported.notna().sum()}/{len(part)} dates. Dose units are unverified; missing records are not zero dose.")
            plot(lines(part,["actual_naoh_dose_reported","planned_naoh_dose_reported"]),key="naoh_"+name)
            st.caption("Sparse records may be reconciliation entries. Coincidence with pH does not establish dosing causality.")
        st.button("Review "+name+" investigations",on_click=navigate,args=("Investigations",name),key="water_cases_"+name)

elif view=="Equipment":
    if equipment.empty: st.info("No equipment records in these dates.")
    for name in plants:
        full=result.equipment.loc[result.equipment.plant.eq(name)]
        part=equipment.loc[equipment.plant.eq(name)]
        if part.empty: continue
        st.subheader(name)
        supported=[c for c in full.select_dtypes("number") if full[c].notna().any() and tag_info(c)["kind"] in ["temperature","vibration","quality","frequency","electrical","recovery"]]
        if not supported: st.info("No mapped continuous signals available.");continue
        linked=cases.loc[cases.plant.eq(name)&cases.signal.isin(supported)]
        priority_tags=list(dict.fromkeys(linked.signal))
        supported=priority_tags+[s for s in supported if s not in priority_tags]
        chosen=st.selectbox("Measurement · "+name,supported,format_func=lambda x:tag_info(x)["asset"]+" · "+tag_info(x)["label"]+" · "+x,key="equipment_"+name)
        info=tag_info(chosen)
        screened=screen(full.set_index("date")[chosen],result.settings["equipment_baseline_days"],result.settings["equipment_iqr_multiplier"])
        scoped=screened.loc[screened.date.between(pd.Timestamp(start),pd.Timestamp(end))]
        marked=result.events.loc[result.events.plant.eq(name)&result.events.signal.eq(chosen)&result.events.date.between(pd.Timestamp(start),pd.Timestamp(end))]
        high=120 if info["kind"]=="temperature" and scoped.value.max()>=100 else None
        a,b,c=st.columns(3)
        observed=scoped.loc[scoped.value.notna()]
        a.metric("Latest in range",display(observed.iloc[-1].value,2) if len(observed) else "Unavailable",border=True,help=info["unit"])
        b.metric("Peak in range",display(scoped.value.max(),2),border=True,help=info["unit"])
        c.metric("Flagged days",str(marked.date.nunique()),border=True,help="Days meeting an investigation rule. Not confirmed faults.")
        st.caption(info["unit"]+" · Original reported values")
        plot(equipment_chart(scoped,info,marked,high),key="equipment_chart_"+name)
        st.caption("Click ‘Prior statistical band’ in the legend to show the reference range.")
        with st.expander("Units, thresholds & coverage"):
            st.write(info["confidence"]+". Electrical registers are not automatically rescaled.")
            if info["kind"]=="temperature":
                st.write("Absolute review above 120 applies only if Celsius and scaling are confirmed.")
            st.caption(f"{int(scoped.flag.sum())} statistical deviations; {int(scoped.status.isin(['Within statistical band','Statistical deviation']).sum())}/{len(scoped)} scored calendar days. Flat references and missing readings are unscored; the band is not an operating limit.")
        relevant=cases.loc[cases.plant.eq(name)&cases.signal.eq(chosen)]
        if len(relevant):
            st.button("Open linked investigation · "+name,on_click=navigate,args=("Investigations",name,relevant.iloc[0].case_id),key="linked_"+name)
        else: st.caption("No qualifying investigation episode for this measurement in the selected dates.")
        with st.expander("Aligned supporting signals · "+name):
            related=[c for c in supported if tag_info(c)["asset"]==info["asset"] and c!=chosen]
            extra=st.multiselect("Compare measurements",related,default=related[:2],max_selections=3,key="related_"+name)
            for signal in extra:
                plot(lines(part,[signal]),key="related_chart_"+name+signal)
            st.caption("Charts share the date interval and retain each measurement's own unit. Similar shapes do not establish causation.")

elif view=="Data & methods":
    st.write("Inspect source coverage, assumptions and the calculation trail. Restore a saved work log here.")
    st.subheader("Restore operator work log")
    st.caption("Exported logs preserve saved reviews across browser sessions. They are not a shared work-order database.")
    log=st.file_uploader("Previously exported work log",type="json",key="worklog_upload")
    if log and st.button("Restore saved reviews"):
        try:
            restored=import_worklog(log.getvalue(),result.fingerprint,set(result.cases.case_id))
            st.session_state.reviews.update(restored);st.session_state.revision+=1
            st.success(f"Restored {len(restored)} review(s). Matching case records replace this session's saved versions.")
        except (ValueError,TypeError,KeyError) as exc: st.error(str(exc))
    st.subheader("Source coverage")
    st.dataframe(pd.DataFrame(result.manifest)[["file","source_rows","rows","first_date","last_date"]],hide_index=True,width="stretch")
    st.caption("Source and channel audits cover complete files, independent of the date filter. Availability is measured after parsing and before application-range exclusions.")
    source=st.selectbox("Source file",list(FILES),key="audit_source")
    status=st.multiselect("Channel availability",["VARIABLE","CONSTANT","MISSING"],default=["VARIABLE","CONSTANT","MISSING"])
    st.dataframe(result.audit.loc[result.audit.source.eq(source)&result.audit.availability.isin(status)],hide_index=True,width="stretch",height=300)
    with st.expander("Data-quality evidence and parsing decisions"):
        quality=in_scope(result.quality,plant,start,end)
        st.caption(f"{len(quality):,} signal-date checks in the selected scope; repeated flatlines are audit evidence, not separate operator alarms.")
        codes=st.multiselect("Checks to inspect",sorted(result.quality.code.unique()),default=["PHYSICAL_RANGE","COUNTER_DECREASE"])
        st.dataframe(quality.loc[quality.code.isin(codes)],hide_index=True,width="stretch",height=300)
        st.dataframe(result.parsing,hide_index=True,width="stretch")
        st.write("Exact duplicate rows are removed and counted. Conflicting plant/date keys stop processing. Missing tokens and nonfinite numbers become missing; invalid tokens are logged. Configured range exclusions retain raw evidence. No forward filling of chemistry, interpolation of missing days, or automatic electrical rescaling is performed.")
    with st.expander("Rule registry and assumptions"):
        st.dataframe(pd.DataFrame([dict(code=k,family=v[0],title=v[1],rule=v[3]) for k,v in PROCESS_RULES.items()]),hide_index=True,width="stretch")
        st.write("Equipment: immediate review above 120 only under an assumed Celsius scale; persistent upward changes above the previous 14-calendar-day Q3 + 1.5×IQR for 3 consecutive days. Missing days reset persistence. Known zero speed suppresses relative trend rules. A flat baseline remains unscored.")
        st.write("All numeric thresholds are prototype review policies. Temperature units, physical asset mapping, product specifications and operating modes require engineering confirmation. None is a manufacturer-certified alarm limit.")
        st.json(result.settings)
    with st.expander("Model coverage and training history"):
        st.caption("Unusualness scores are exploratory; they are not failure probabilities. Different detector coverage is not directly comparable.")
        st.dataframe(daily[["plant","date","model_status","available_detectors","statistical_score","pca_score","isolation_score","ensemble_score","multivariate_train_through"]],hide_index=True,width="stretch")
        st.dataframe(pd.DataFrame(result.training).astype(str),hide_index=True,width="stretch")
        st.write("PCA and Isolation Forest require 28 earlier eligible rows. Imputation and scaling are fitted only on earlier data. These process models use output, SEC, conductivity passage and product pH. No confirmed failure labels or measured early-warning accuracy are available.")
    with st.expander("Reproducibility and engineering references"):
        st.code(result.fingerprint,language=None)
        st.dataframe(pd.DataFrame(result.manifest),hide_index=True,width="stretch")
        st.markdown("[DuPont RO/NF technical manual](https://www.dupont.com/content/dam/dupont/amer/us/en/water-solutions/public/documents/en/RO-NF-FilmTec-Manual-45-D01504-en.pdf) · [SKF bearing investigation](https://www.skf.com/binaries/pub12/Images/0901d1968064c148-Bearing-failures---14219_2-EN_tcm_12-297619.pdf)")
        st.caption("References support investigation concepts, not this prototype's numerical thresholds. Verified pressure, normalized flow, maintenance outcomes and current telemetry are still needed.")
    st.download_button("Download reproducible analysis bundle",analysis_bundle(result),"BlueNexus_analysis.zip","application/zip",type="primary")
    st.caption("The analysis bundle includes derived plant data and must follow the dataset's confidentiality restrictions.")

st.caption(f"BlueNexus · v{VERSION} · Historical decision support")

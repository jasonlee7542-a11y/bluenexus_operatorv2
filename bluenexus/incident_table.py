"""Accessible incident rows with hover, keyboard activation and stable case IDs."""
import streamlit as st

_TABLE=st.components.v2.component(
    "bluenexus_incident_table",
    html='<div class="scroll"><table aria-label="Investigation queue"><colgroup><col class="col-priority"><col class="col-incident"><col class="col-plant"><col class="col-date"><col class="col-days"><col class="col-open"></colgroup><thead><tr><th>Priority</th><th>Investigation</th><th>Plant</th><th>Flagged period</th><th class="number">Days</th><th><span class="sr">Open</span></th></tr></thead><tbody></tbody></table></div>',
    css="""
    .scroll {overflow-x:auto; border:1px solid #d8e4ec; border-radius:12px; background:#fff;}
    table {border-collapse:collapse; table-layout:fixed; width:100%; min-width:960px; font:14px var(--st-font,sans-serif); color:#173349;}
    /* Preserve the measured proportions of the original four-row preview. */
    .col-priority {width:17.89%;}
    .col-incident {width:37.36%;}
    .col-plant {width:10.40%;}
    .col-date {width:18.75%;}
    .col-days {width:8.07%;}
    .col-open {width:7.53%;}
    th {background:#153b55; color:#fff; text-align:left; padding:14px 16px; font-size:12px; font-weight:650; letter-spacing:.3px; white-space:nowrap;}
    td {padding:15px 16px; border-bottom:1px solid #e5edf2; vertical-align:middle;}
    tbody tr:nth-child(even) {background:#f7fafc;}
    tbody tr {cursor:pointer; transition:background .12s;}
    tbody tr:hover,tbody tr:focus-within {background:#e4f3f5; box-shadow:inset 4px 0 #087f8c;}
    tbody tr:last-child td {border-bottom:0;}
    .pill {display:inline-block; border-radius:5px; padding:5px 8px; font-size:12px; font-weight:650; white-space:nowrap;}
    .urgent {background:#fce5e9; color:#a7273a;}
    .review {background:#fff0ce; color:#805200;}
    .data {background:#e3f2fb; color:#175d7c;}
    .incident {font-weight:650; overflow-wrap:anywhere; line-height:1.5;}
    .date {color:#536b7c; font-size:12px; white-space:nowrap;}
    .plant {white-space:nowrap; font-weight:600;}
    .number {text-align:right; font-variant-numeric:tabular-nums;}
    button {font:inherit; color:#087f8c; border:0; background:transparent; cursor:pointer; border-radius:4px; padding:5px; font-size:20px;}
    button:focus-visible {outline:2px solid #087f8c; outline-offset:2px;}
    .sr {position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;}
    """,
    js="""
    export default function({data,parentElement,setTriggerValue}) {
      const body=parentElement.querySelector('tbody');
      body.replaceChildren();
      for(const row of data.rows) {
        const tr=document.createElement('tr');
        tr.dataset.caseId=row.id;
        const cell=(text,cls='')=>{const td=document.createElement('td');td.className=cls;td.textContent=text;tr.append(td);return td;};
        const priority=cell('');
        const badge=document.createElement('span');
        badge.className='pill '+(row.priority==='Verify promptly'?'urgent':row.priority==='Investigate'?'review':'data');
        badge.textContent=row.priority;priority.append(badge);
        cell(row.title,'incident');cell(row.plant,'plant');cell(row.period,'date');cell(row.days,'number');
        const action=cell('');const button=document.createElement('button');
        button.type='button';button.textContent='→';
        button.setAttribute('aria-label','Investigate '+row.plant+': '+row.title+' · '+row.period);
        action.append(button);
        tr.onclick=()=>setTriggerValue('opened',row.id);
        body.append(tr);
      }
    }
    """,
)

def queue_records(cases):
    return [dict(id=r.case_id,priority=r.priority,title=r.title,plant=r.plant,
                 period=f"{r.start:%d %b} – {r.end:%d %b %Y}",days=int(r.days))
            for r in cases.itertuples()]

def incident_table(cases,on_open,key="incident_queue"):
    allowed=set(cases.case_id)
    def opened():
        case_id=st.session_state[key].opened
        if case_id in allowed:
            on_open(case_id)
    return _TABLE(data={"rows":queue_records(cases)},key=key,on_opened_change=opened)

_SCROLL_TOP=st.components.v2.component(
    "bluenexus_scroll_top",
    html='<div aria-hidden="true"></div>',
    css="div { width:0; height:0; overflow:hidden; }",
    js="""
    export default function({data}) {
      if(data?.top) requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'instant'}));
    }
    """,
)

def scroll_to_top(*,key="investigation_scroll_top"):
    return _SCROLL_TOP(data={"top":True},key=key)

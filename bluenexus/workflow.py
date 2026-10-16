"""Operator-entered verification. No inferred current state or dispatch API."""
import json
from datetime import datetime, timezone
from bluenexus.playbooks import playbook

CURRENT = ["Not checked", "Confirmed in current evidence", "Absent in current evidence"]
OUTCOMES = ["Checks incomplete", "Still unexplained", "Explanation verified"]

def recommendation(case, review):
    current = review.get("current", CURRENT[0])
    outcome = review.get("outcome", OUTCOMES[0])
    if current == CURRENT[0]:
        return "Verify current condition", "Obtain current readings, timestamps and tag identity before an attendance decision. Historical evidence alone cannot establish current need."
    if not review.get("evidence", "").strip():
        return "Record verification evidence", "Add the reading, timestamp and source supporting your answer before relying on a routing recommendation."
    if current == CURRENT[2]:
        return "Historical follow-up", "The operator reports the condition is absent. Retain the evidence and follow-up plan; absence does not prove repair."
    if outcome == OUTCOMES[2]:
        return "Remote follow-up", "Record the verified explanation and the next review time. No physical repair is inferred."
    if case["priority"] == "Verify promptly":
        return "Contact site / engineering", "A current priority condition is reported. Seek prompt verification under the site's established escalation procedure."
    if outcome == OUTCOMES[0]:
        return "Complete remote checks", "Work through the checklist and record the result before deciding whether attendance is needed."
    team = "instrumentation" if case["family"] == "data" else "sampling / instrumentation" if case["family"] == "quality" else "site engineering"
    return "Targeted inspection recommended", f"The current condition remains unexplained. Prepare an inspection for {team}, confirming the physical asset before assignment."

def worklog_payload(records, fingerprint):
    return json.dumps(dict(schema_version=1, fingerprint=fingerprint, records=records),indent=2,ensure_ascii=False).encode("utf-8")

def import_worklog(payload, fingerprint, case_ids):
    if len(payload) > 2_000_000:
        raise ValueError("Work log exceeds 2 MB")
    data = json.loads(payload)
    if not isinstance(data,dict) or data.get("schema_version") != 1 or data.get("fingerprint") != fingerprint:
        raise ValueError("Work log must match this analysis version, source files and settings.")
    records = data.get("records")
    if not isinstance(records,dict):
        raise ValueError("Work log records must be an object")
    allowed = {"current","outcome","evidence","owner","asset","notes","followup","updated_at"}
    for key,value in records.items():
        if key not in case_ids or not isinstance(value,dict) or set(value)-allowed:
            raise ValueError("Unknown investigation or work-log fields")
        if any(not isinstance(v,str) or len(v)>20000 for v in value.values()):
            raise ValueError("Work-log values must be text up to 20,000 characters")
        if value.get("current",CURRENT[0]) not in CURRENT or value.get("outcome",OUTCOMES[0]) not in OUTCOMES:
            raise ValueError("Invalid verification answer")
    return records

def handoff(case, review, result):
    book=playbook(case["family"],case["asset"])
    route,reason=recommendation(case,review)
    lines=["# BlueNexus investigation handoff",f"Case: {case['case_id']}",f"Plant: {case['plant']} | Candidate asset: {case['asset']}",
           f"Confirmed asset: {review.get('asset') or 'Not recorded'}",f"Historical flag period: {case['start']:%Y-%m-%d} to {case['end']:%Y-%m-%d}",
           f"Issue: {case['title']}",f"Rule: {case['threshold']}",f"Interpretation: {case['confidence']}",
           "## Latest qualifying evidence",json.dumps(case['evidence'],indent=2,default=str),
           "## Operator verification",f"Current condition: {review.get('current',CURRENT[0])}",f"Remote result: {review.get('outcome',OUTCOMES[0])}",
           f"Verification evidence: {review.get('evidence') or 'Not recorded'}",f"Owner: {review.get('owner') or 'Unassigned'}",
           f"Follow-up: {review.get('followup') or 'Not recorded'}",f"Last saved (UTC): {review.get('updated_at') or 'Not saved'}",
           f"Recommended next action: {route}. {reason}","## First inspection location",book['location'],"## Remote checks"]
    lines += [f"{i}. {x}" for i,x in enumerate(book['remote'],1)]
    lines += ["## Technician checks"]+[f"{i}. {x}" for i,x in enumerate(book['site'],1)]
    lines += ["## Possible explanations (unconfirmed)"]+book['causes']+["## Missing evidence",book['missing'],"## Notes",review.get('notes') or 'None',
              "## Reproducibility",f"Analysis fingerprint: {result.fingerprint}",json.dumps(result.manifest,indent=2),json.dumps(result.settings,indent=2),
              "No dispatch or plant commands were sent. Follow approved site/OEM procedures. No verified failure labels are available."]
    return "\n\n".join(lines)

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

"""Investigation guidance, not certified maintenance instructions or control commands."""
SOURCES={
 'RO guidance':'https://www.dupont.com/content/dam/dupont/amer/us/en/water-solutions/public/documents/en/RO-NF-FilmTec-Manual-45-D01504-en.pdf',
 'Bearing guidance':'https://cdn.skfmediahub.skf.com/api/public/0901d1968024f02a/pdf_preview_medium/0901d1968024f02a_pdf_preview_medium.pdf'}

BOOKS={
 'temperature':dict(
  location='The temperature sensor and associated bearing/housing on {asset}. Confirm the tag-to-asset mapping before attendance.',
  causes=['Sensor scaling, probe or wiring problem','Changed load, cooling or ambient conditions','Mechanical heating; lubrication or alignment issues require confirmation'],
  remote=['Confirm the latest timestamp, °C scaling and sensor identity; a historical record is not a current alarm.', 'Compare same-pump frequency/current and vibration where available; review operator alarms and recent maintenance.', 'Ask for an independent temperature measurement if the live value remains abnormal.'],
  site=['Confirm sensor location; compare its reading with an appropriate independent temperature measurement.', 'Inspect sensor attachment/wiring and visible cooling obstructions. Check lubrication records and signs of leakage.', 'If heating is confirmed, a qualified technician should assess bearings, loading and alignment using the OEM procedure. Both too little and too much lubricant can cause problems.'],
  trigger='Prompt site/engineering verification if the high reading is current and corroborated, or if a current severe reading cannot be reliably verified remotely. Follow existing plant alarm procedures.',
  ai='Summarise trends and retrieve alarms, tag configuration and maintenance history if connected. An AI assistant cannot verify a bearing physically or repair a sensor.',
  missing='Verified sensor location, OEM temperature limits, live readings and independent measurement.',source='Bearing guidance'),
 'vibration':dict(
  location='{asset}: sensor mounting point, motor/pump bearing housings, coupling/base and suction-side instrumentation; asset identity must be verified.',
  causes=['Different speed or process load','Loose or faulty sensor mounting','Mechanical or hydraulic change; alignment, looseness or cavitation cannot be distinguished from these daily values'],
  remote=['Check live run state and speed; compare periods at similar speed and throughput.', 'Review vibration axes, temperature and motor current together. Look for maintenance or switching events.', 'Request higher-frequency vibration data and suction/discharge readings before diagnosing a component.'],
  site=['Verify sensor attachment and repeat measurements at documented bearing locations and comparable speed.', 'A qualified technician should assess mounting/base condition, coupling alignment and bearing condition.', 'Check suction restriction/air ingress indicators and inlet pressure against operating records; do not infer cavitation from one vibration value.'],
  trigger='Arrange inspection when a persistent change is confirmed at comparable operating conditions, especially with independent temperature/current/noise evidence.',
  ai='Compare historical signals, run states and maintenance logs; draft a handoff. Physical vibration measurement and mechanical inspection require personnel.',
  missing='Confirmed units and RMS/peak convention, equipment speed/load, waveform/spectrum and pressure measurements.',source='Bearing guidance'),
 'energy':dict(
  location='Start with plant electricity and product-water meters. If excess consumption is confirmed, inspect pump/VFD operating records and RO feed, concentrate and permeate measurement points.',
  causes=['Lower output while fixed electrical loads continue','Changed runtime, cleaning schedule or feed conditions','Meter/aggregation mismatch; hydraulic resistance is a hypothesis requiring pressure/flow evidence'],
  remote=['Check product volume and electricity totals cover the same period and plant boundary.', 'Compare similar-output days; review demand, hours running and cleaning/standby logs.', 'Compare feed conductivity/temperature and measured pressure/flow if available. Identify which load changed before considering an adjustment.'],
  site=['Verify electricity and product-meter readings against local instruments.', 'If high energy intensity persists at comparable operation, record pump suction/discharge and RO stage pressures/flows.', 'Assess prefilter restriction, valve positions and equipment condition under the approved SOP. Evaluate membrane cleaning only after appropriate normalized performance checks.'],
  trigger='Remote review first. Arrange targeted inspection if excess energy persists after operating conditions and meter boundaries are reconciled, or corroborating mechanical/pressure evidence appears.',
  ai='Reconcile totals, compare similar periods and gather schedules/readings if integrated. Approved scheduling changes may be remote; this app has no control connection.',
  missing='Operating hours, demand/cleaning state, feed conditions, calibrated flow/pressure data and verified meter boundaries.',source='RO guidance'),
 'delivery':dict(
  location='Reclaimed-water supply meter, customer-end meter and any intervening storage tanks or branch connections.',
  causes=['Different meter timestamps or reporting boundaries','Tank filling/emptying or unrecorded branches','Meter issue or actual loss; leakage is not confirmed'],
  remote=['Align both meter periods and check units/reset events.', 'Reconcile storage level changes and known transfers/branches.', 'Ask whether the discrepancy remains in current readings after reconciliation.'],
  site=['Compare local meter displays with remote totals and check instrument condition.', 'Inspect storage levels and the documented transfer route for unexplained transfers or visible loss.', 'Escalate a persistent unexplained balance to the site supervisor; do not label the historical gap as proven leakage.'],
  trigger='Site verification if a current large discrepancy remains unexplained after time, storage and boundary checks.',
  ai='Reconcile timestamps, totals and tank inventory records. Physical leak investigation or meter repair requires a technician.',
  missing='Meter boundaries, tank inventory changes and aligned interval totals.',source=None),
 'recovery':dict(
  location='Feed and product flowmeters, associated storage boundaries, and RO train feed/permeate/concentrate measurement points.',
  causes=['Unmatched reporting periods or storage inventory change','Flowmeter mapping/scaling issue','Process operating change; whole-plant recovery is not identical to membrane recovery'],
  remote=['Confirm numerator/denominator units and aligned periods.', 'Separate whole-plant volume recovery from equipment RO recovery; reconcile any storage changes.', 'Compare feed/product volumes and operating/cleaning logs before interpreting membrane performance.'],
  site=['Verify local flowmeter readings and calibration history.', 'Record feed, product and concentrate flows over the same interval and check the water balance.', 'If process deterioration is suspected, obtain pressure, temperature and quality measurements for an engineering review.'],
  trigger='Site instrument/process checks if a current discrepancy persists after remote reconciliation.',
  ai='Check calculations, periods and inventory reconciliation. It cannot certify flowmeter accuracy remotely.',
  missing='Aligned flow periods, storage changes and verified plant versus RO measurement boundaries.',source='RO guidance'),
 'quality':dict(
  location='Product-water sample point and pH/conductivity/turbidity instrument; then relevant pretreatment and RO train sample points.',
  causes=['Instrument calibration, temperature compensation or sampling issue','Changed feedwater quality or mixing','Treatment performance change requiring confirmatory sampling'],
  remote=['Verify measurement units, timestamps and sample-point identity.', 'Review instrument calibration, feedwater trends and recent chemical/cleaning logs.', 'Request an independent product sample if the current reading remains outside the site-approved range.'],
  site=['Verify sample point and repeat measurement with a suitable calibrated instrument.', 'Check probe/sample-line condition and calibration according to the instrument SOP.', 'If confirmed, follow the site quality-response procedure and investigate upstream treatment with the responsible engineer.'],
  trigger='On-site sampling/instrument verification if an abnormal current result cannot be resolved remotely. Product suitability must follow the site-specific quality procedure.',
  ai='Cross-check records and identify coincident process changes. It cannot replace sampling, certify water safety or select a chemical dose from these data.',
  missing='Site product specification, verified sampling points, calibration and confirmatory laboratory/field result.',source='RO guidance'),
 'data':dict(
  location='The source instrument, PLC tag mapping and historian/export path for {asset}.',
  causes=['Reset, scaling or aggregation mismatch','Stale/unmapped channel','Incorrect measurement association; a physical fault is not established'],
  remote=['Check tag definition, units/scaling and update timestamps.', 'Compare historian records with the daily export and reset/configuration logs.', 'Verify that compared signals belong to the same equipment and time interval.'],
  site=['If unresolved, compare the local instrument display with the PLC and historian value.', 'Have qualified instrumentation personnel inspect/calibrate the relevant sensor under the approved procedure.'],
  trigger='Remote data/configuration investigation first; instrument attendance only if the mismatch cannot be reconciled remotely.',
  ai='Audit records, detect resets and prepare corrected-data proposals for review. No automatic raw-data overwrite or PLC configuration change is implemented.',
  missing='Confirmed tags, scaling, sample timing and reset/configuration records.',source=None)
}

def playbook(family,asset):
    b=dict(BOOKS.get(family,BOOKS['data']));b['location']=b['location'].format(asset=asset)
    return b

def route(family,priority,current,checks):
    if current=='Not confirmed in latest readings':return 'Historical review only','No technician dispatch is justified by this historical incident alone. Keep the evidence and record the verification outcome.'
    if current=='Not checked':return ('Verify current condition promptly' if priority=='Verify promptly' else 'Remote verification first'),'Check current readings and alarms before making an attendance decision. If a current severe condition cannot be checked remotely, escalate under the site SOP.'
    if checks=='Explained by records / independent verification':return 'Remote follow-up','Document the verified explanation and continue monitoring. Do not mark equipment repaired solely because a statistical flag disappears.'
    if priority=='Verify promptly':return 'Site / engineering verification recommended','A current high-priority condition is reported. Contact the responsible engineer/site team and follow the existing alarm procedure.'
    if checks=='Still unexplained after checks':return 'Targeted site inspection recommended','Use the inspection locations and checklist below. Confirm the asset mapping before assigning the work.'
    return 'Complete remote checks','Use the remote checklist before deciding whether physical verification is necessary.'

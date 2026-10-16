# Five-minute walkthrough

Opening: “We turn daily plant records into prioritized investigations. Every case
shows the evidence, what remains uncertain and the next verification step.”

1. Load all three CSVs. On Operations, point to historical date coverage and the
   prioritized queue. Counts are rule episodes, not unresolved live alarms.
2. Open **Guided walkthrough → Why high SEC does not automatically justify a visit**.
   Plant A, 31 August: 1,881 m³, 3,660 kWh, SEC 1.946 against plan 1.200 (+62.1%).
   Earlier load model estimate ≈3,350 kWh; actual is ≈9.2% above it. Only two peer
   days; a five-peer comparison is unavailable. Investigate demand, runtime and
   meter boundaries before attributing a fault. The model does not prove the cause.
3. Return to Operations and open **Reconcile a large delivery discrepancy**.
   Plant B, 11 August: 21,187 m³ supply versus 973 m³ customer volume, a 20,214 m³
   discrepancy (95.4%). Follow the three remote checks. Explain alternative causes.
4. Show Record verification and Technician handoff. Leave current condition as
   Not checked unless you have real independent evidence. If demonstrating the
   decision tree with hypothetical answers, explicitly say they are hypothetical
   and label the verification evidence “DEMONSTRATION ONLY”. Export a draft handoff.
5. Show **Verify an extreme temperature reading**. Plant A, 1–27 January, about
   212.7 in assumed Celsius units. First verify units and the sensor, then current
   condition. No bearing failure is proven. Explain the outside-period warning.
6. For the AI engineer: Data & methods → training history and source hashes. Show
   that references use earlier observations, missing coverage stays unavailable,
   and scores do not become failure probabilities. Export the reproducible bundle.

Executive message: focused attention, evidence-based attendance and clearer
technician preparation. Reduced downtime/visits remain outcomes to validate.

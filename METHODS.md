# Methods and interpretation

## One preparation path

Three CSV byte payloads enter `ingestion/sanitizer.py`. Exact duplicate rows are
removed and counted; remaining duplicate plant/date keys stop processing. Missing
tokens are normalized, invalid/nonfinite numeric tokens logged and made missing.
Original files are never modified. Source SHA-256 hashes, row counts and periods
are retained. Date formats are explicitly year-first ISO/slash or US MM/DD/YYYY;
ambiguous slash dates use that documented US convention.

Configured application ranges quarantine negative volume/energy/conductivity/dose,
pH outside 0–14, RO/UF percentages outside 0–100 and reported recovery outside
0–1. These are application assumptions, not universal physical/safety limits.
Frequency is only screened for negativity; the earlier arbitrary 65 Hz ceiling
has been removed. Raw evidence remains available. Counter decreases yield missing
deltas. Flatline candidates are audit evidence, not presumed dead sensors.

## Energy comparisons

SEC = daily electricity / product volume. Nonpositive denominators yield missing.
Period SEC divides totals on matching valid dates, not the average of daily ratios.
Plan gaps are reference comparisons; positive-only gaps are distinct from net gaps.

Peer comparison: same plant, prior 60 calendar days, output within ±20%, at least
five eligible records, excluding standby-indicated days. Median peer SEC is used.
No future records enter a peer reference. It does not control feedwater or runtime.

Load estimate: nonnegative fixed kWh/day plus nonnegative kWh/m³ × output. Fit on
at least 14 earlier eligible records, refreshed every seven evaluation rows.
The first reading in each batch is later than its training cutoff. The +20%
residual rule requires two adjacent calendar days.

## Equipment and process cases

Broad equipment checks use the parsed raw values so suspect observations remain
visible. Temperature above 120 triggers verification only under assumed Celsius
units. Temperature, vibration and turbidity upward trends use prior 14-calendar-day
Q3 + 1.5 IQR, at least 12 earlier observations, and three adjacent flagged days.
Flat references receive no IQR decision. Known zero pump frequency suppresses
relative trend checks; unknown run state remains unverified. The first case day
is the first day satisfying persistence, not a retrospectively backdated warning.

Process rules retain Yuwei's plan/load/quality/recovery policies, with a separate
matched-output rule. All qualifying days enter one case schema. Consecutive days
are grouped by plant, rule and signal. Gaps break episodes. Priority is the highest
priority observed within the episode; displayed evidence is the last qualifying
day, and full daily evidence remains available. Different rules remain separate
investigations because their reference comparisons differ; counts are not counts
of distinct physical faults. Repeated quality audit checks are kept out of the
default process/equipment queue, with invalid-range and counter cases available
under Data consistency.

## Exploratory models

Lagged EWMA/trailing spread and historical PCA/Isolation Forest are retained.
Multivariate features are product volume, SEC, conductivity passage and product
pH. Historical imputation/scaling only; at least 28 eligible training rows; current
rows require at least three process features. Models refit every seven rows.
Statistical process windows are observation-based; equipment IQR windows are
calendar-based. Missing calendar dates break case persistence in both paths.
These models provide no calibrated failure probability or proven warning lead time.

## Attendance logic

Current condition starts Not checked. An operator must record verification evidence
before a recorded current/absent result supports routing. Confirmed priority cases
request site/engineering contact; unresolved ordinary cases recommend targeted
inspection after checks; verified explanations lead to remote follow-up. Quality
and data cases request relevant sampling/instrumentation review. The prototype
does not independently verify entered evidence, assign a work order or send commands.

## Still needed for operational adoption

Verified asset IDs/locations, OEM/site setpoints, calibrated instruments, live
telemetry, run/cleaning states, operating hours, normalized RO pressure/flow data,
maintenance outcomes, authentication and a shared audit/work-order system.

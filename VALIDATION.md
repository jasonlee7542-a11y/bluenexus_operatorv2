# Validation record

Reviewed locally on 16 October 2026 using Python 3.13 on Windows, Streamlit 1.66.0,
Polars 2.0.0, pandas 3.0.6, NumPy 2.5.4, scikit-learn 1.9.1, Plotly 7.1.0 and
PyArrow 26.0.0. Direct runtime dependencies are pinned in requirements.txt.

## Automated checks

18 automated checks:

- Actual Plant A 31 August energy arithmetic, historical load residual and missing
  peer comparison agree with independent calculations.
- The 27-day January Plant A temperature episode survives a flat/extreme baseline.
- Production is the first Operations section. Hidden January temperature evidence
  is disclosed in a compact date-context expander on every view;
  its shortcut opens the full equipment history with the correct measurement.
  The rendered chart contains all 27 original readings between 212 and 213.
- Plant B delivery discrepancy arithmetic and percent display/export units agree.
- Peer references exclude the current/future observations.
- Appending later data does not change earlier qualifying events.
- Calendar gaps break case grouping; within-episode priority escalation is retained.
- Empty results retain a usable schema.
- Routing requires operator evidence before a current-condition answer is actionable.
- Work-log restoration rejects wrong datasets, unknown cases and invalid answers.
- Analysis archive contains its provenance and source files retain their hashes.
- All six views render for All plants, Plant A and Plant B.
- Guided links retain the selected investigation through reruns.
- Investigation filters and out-of-range flags remain accessible in the sidebar;
  filtering to an empty queue preserves the controls needed to recover.
- Browse all cases expands every in-scope row on Operations and collapses back
  to the four-row preview without navigating away.
- Equipment-only date ranges do not fabricate performance data.
- Fixed Plant A recovery is a metric, avoiding floating-point jitter visualization.
- Saved verification survives navigation and updates the recommendation.

## Browser checks

Headless Microsoft Edge at 1440×1000 and a 390×844 mobile viewport:

- Inspected operations, investigations, energy, water, equipment and methods views.
- Reviewed evidence layout, remote checks, conditional units and technician guidance.
- Downloaded the investigation handoff.
- Confirmed mobile page has no document-level horizontal overflow; navigation wraps.
- Extracted the GitHub ZIP to a separate folder without plant CSVs and started it.
- Confirmed explicit empty-data startup and rejection of partial dataset uploads.
- Uploaded all three CSVs, visited all six views without application exceptions.
- Saved a review, downloaded its JSON work log and restored that work log.
- Refreshed visual design: semantic colour cards, navy sidebar, distinct heading
  and body fonts, compact investigations, tabbed energy charts and collapsible
  explanations. Inspected desktop and mobile layouts and the QZ history shortcut.
- Sidebar now follows Yuwei's light blue, centered logo and filter-first pattern,
  with coverage and upload/work-log controls grouped in collapsible sections.
- Equipment bands are optional legend layers, so extreme statistical bounds do
  not compress the initial raw-value chart. Original readings remain unchanged.
- Operations uses a CCv2 incident table with colour-coded priorities, aligned
  dates/counts, row hover and case-ID navigation. Browser checks verified mouse
  activation, keyboard Enter, all 44 in-scope rows, collapse, and mobile overflow
  containment. Source values use DOM textContent, not interpolated HTML.

## Investigation layout references

- [IBM Carbon disclosure patterns](https://www.carbondesignsystem.com/building-blocks/core/patterns/disclosures):
  secondary filters and interactive details in compact popovers.
- [Grafana dashboard guidance](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/):
  organise the page around the operational question and reduce cognitive load.

Applied as sidebar queue controls, one case selector, evidence and action columns,
and local popovers for supporting details. No filters or historical evidence were removed.

The source directories used for comparison were not modified by this build. No
app or repository was published. Streamlit Community Cloud/Linux deployment has
not been executed here. These checks establish software behavior, not verified
fault detection, maintenance outcomes, live-system integration or early-warning
accuracy. The project README records the remaining deployment steps and boundaries.

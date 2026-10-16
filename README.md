# BlueNexus Operations Review

A consolidated Challenge 1 dashboard: prior-only process analytics, broader
equipment screening, and an operator workflow from evidence to technician handoff.

**Streamlit entry point: `app.py`. Python: 3.13.**

## Run locally

Open this folder in a terminal:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux, use `python3.13`, then `.venv/bin/python` for the last two commands.
The three supplied CSVs can be placed in `data/raw/`, or uploaded together through
**Data inputs** in the sidebar. The upload replaces the full dataset for that
browser session. Restarting/reloading a hosted session may require re-uploading.

## GitHub and Streamlit Community Cloud

1. Extract `BlueNexus_Unified_GitHub.zip` and upload its **contents** to the root of
   your GitHub repository. Include `bluenexus/`, `assets/`, `static/`,
   `.streamlit/config.toml`, `requirements.txt`, `app.py`, and the supporting docs.
   Enable hidden files in your file manager so `.streamlit` is not missed.
2. In Streamlit Community Cloud, create an app from that repository and branch.
   Set **Main file path** to `app.py` and select **Python 3.13** in advanced settings.
   If uploading the entire folder instead, set the main path to
   `BlueNexus_Unified/app.py`; repository-root contents are recommended.
3. Deploy. No API keys, secrets, LLM service or external database are required.
4. Open the app and upload all three CSVs in **Data inputs**. The ZIP intentionally
   contains no plant dataset. A public code repository does not authorize public
   distribution of the challenge data; use appropriate app access controls.
5. Confirm the date coverage, open each walkthrough and download a sample handoff
   before the presentation. Do not enter invented current readings as real evidence.

Official deployment references: [file organization](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization),
[dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
and [deployment settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

For automatic hosted data loading, an authorized private deployment can include
the three CSVs in `data/raw/`; this requires deliberately overriding `.gitignore`.
Only do this when your dataset permissions permit the chosen repository and app
access. Browser upload is the default delivery path.

## Six views

- **Operations:** prioritized investigations, out-of-period priority history,
  guided walkthroughs and production context.
- **Investigations:** compact evidence, contextual trend, remote checks,
  verification form, attendance recommendation and technician handoff.
- **Energy:** supplied plan, earlier similar-output peers and historical load
  estimate, each with explicit coverage and interpretation.
- **Water & quality:** plant/RO recovery, supply/customer reconciliation,
  conductivity, pH and available chemical records.
- **Equipment:** both plants' mapped signals, original units, prior IQR bands,
  investigation markers and aligned supporting trends.
- **Data & methods:** source audit, exclusions, rules, model coverage, training
  history, reproducible ZIP and work-log restoration.

## Operator notes and persistence

Use **Save verification and update recommendation** to commit form answers to the
session. Unsaved form edits are not retained when changing pages. Export the
**work log** in the sidebar before leaving. Restore it in **Data & methods**.
Restoration checks the dataset/settings/version fingerprint and case identifiers.
This is a portable review record, not a shared work-order database. Download the
Markdown handoff for the responsible team; the app sends no messages or commands.

## Analytical boundary

The app analyzes historical daily records only. There are no verified failure
labels, live measurements or independently verified repair outcomes. Priorities
are provisional review policies. Sensor identities, units and physical locations
remain candidates. An assumed Celsius threshold is displayed as conditional;
electrical registers are never silently rescaled.

The load estimate and peer comparison control for output only, not operating
hours, feedwater, cleaning or equipment condition. PCA/Isolation Forest scores
are exploratory and appear in the methods view, not as plant safety ratings.
Incident dates are qualifying days; a last flag does not establish resolution.
No control, chemical-dose adjustment, automatic dispatch, monetary saving or
causal AI-related savings claim is made.

## Reproduce and check

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests using the confidential CSVs skip if the files are not present; synthetic
checks still run. The UI supports a clean GitHub deployment without these files.
See `METHODS.md`, `DEMO_GUIDE.md`, `VALIDATION.md` and `PROVENANCE.md`.

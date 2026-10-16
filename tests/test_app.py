from pathlib import Path
import sys
import pytest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

@pytest.fixture
def app():
    if not (ROOT/"data/raw/plant_daily_performance.csv").exists():
        pytest.skip("Restricted challenge CSVs not present")
    return AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()

def test_every_view_renders_for_both_plants(app):
    for plant in ["All plants","Plant A","Plant B"]:
        app.selectbox(key="plant").select(plant).run()
        for page in ["Operations","Investigations","Energy","Water & quality","Equipment","Data & methods"]:
            app.session_state["view"]=page
            app.run()
            assert not app.exception,[(x.message) for x in app.exception]

def test_deep_link_keeps_selected_case_through_reruns(app):
    buttons=[b for b in app.button if b.label=="Why high SEC does not automatically justify a visit"]
    buttons[0].click().run()
    assert app.session_state["view"]=="Investigations"
    selected=app.selectbox(key="selected_case").value
    assert any("High energy intensity" in x.value for x in app.subheader)
    app.run()
    assert app.selectbox(key="selected_case").value==selected
    assert not app.exception

def test_empty_scope_is_explicit(app):
    app.selectbox(key="period").select("Custom dates").run()
    import datetime
    app.date_input(key="dates").set_value((datetime.date(2026,1,1),datetime.date(2026,1,3))).run()
    app.session_state["view"]="Energy"
    app.run()
    assert not app.exception
    assert any("No performance records" in x.value for x in app.info)

def test_fixed_recovery_is_a_metric_not_a_jitter_chart(app):
    app.selectbox(key="plant").select("Plant A").run()
    app.session_state["view"]="Water & quality";app.run()
    recovery=[m for m in app.metric if m.label=="Reported volume recovery"]
    assert recovery[0].value=="75.0%"
    assert not app.exception

def test_save_evidence_and_revisit_preserves_review(app):
    [b for b in app.button if b.label=="Reconcile a large delivery discrepancy"][0].click().run()
    selected=app.selectbox(key="selected_case").value
    [x for x in app.selectbox if x.label=="Current condition"][0].select("Confirmed in current evidence")
    [x for x in app.selectbox if x.label=="Remote investigation result"][0].select("Still unexplained")
    [x for x in app.text_area if x.label.startswith("Verification evidence")][0].set_value("TEST ONLY: meter readings checked at 10:00")
    [b for b in app.button if b.label=="Save verification and update recommendation"][0].click().run()
    assert not app.exception
    assert app.session_state["reviews"][selected]["current"]=="Confirmed in current evidence"
    assert any("Contact site / engineering" in x.value for x in app.markdown)
    app.session_state["view"]="Energy";app.run()
    app.session_state["view"]="Investigations";app.run()
    assert app.session_state["reviews"][selected]["evidence"].startswith("TEST ONLY")

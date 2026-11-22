"""Run with: python -m streamlit run app.py"""
import os
from deployment import get_setting, guard_live
import streamlit as st
from support import MAX_MESSAGE_LENGTH, SupportError, evaluate, load_samples, make_request

st.set_page_config(page_title="Jev support desk", page_icon="💬", layout="centered")
live_enabled = str(get_setting(st, "ENABLE_LIVE", "false")).lower() == "true"
api_key = str(get_setting(st, "TYPESAFE_API_KEY", "")).strip()
model = str(get_setting(st, "TYPESAFE_MODEL", "jev-latest"))
if api_key:
    os.environ["TYPESAFE_API_KEY"] = api_key
st.title("Customer support assistant")
st.write("Evaluate a ticket, recommend a team, and prepare a reply for an agent to review.")
samples = {item["id"]: item for item in load_samples()}
mode = st.sidebar.radio("Evaluation mode", (["Demo examples", "Live Jev"] if live_enabled else ["Demo examples"]), key="mode")
demo = mode == "Demo examples"
if not live_enabled:
    st.sidebar.caption("This deployment offers demo examples only.")
if demo:
    st.info("Demo mode replays invented example results. It makes no API calls and cannot evaluate new messages.")
else:
    st.info("Live mode sends the entered ticket to TypeSafe. Each submission can use API credits.")
if not demo and not os.environ.get("TYPESAFE_API_KEY", "").strip():
    st.warning("No API key found. Configure TYPESAFE_API_KEY in host Secrets, then restart this app.")

selected = st.selectbox("Example ticket", list(samples), format_func=lambda key: samples[key]["title"], key="sample")
# Reset the editor and old results before the text widget is instantiated.
if st.session_state.get("loaded_sample") != selected:
    st.session_state.message = samples[selected]["state"]["ticket"]["message"]
    st.session_state.loaded_sample = selected
    st.session_state.pop("evaluation", None)

with st.form("ticket_form"):
    message = st.text_area("Customer message", height=170, max_chars=MAX_MESSAGE_LENGTH, key="message")
    submitted = st.form_submit_button("Evaluate ticket")

if submitted:
    st.session_state.pop("evaluation", None)
    try:
        if not demo:
            guard_live(st.session_state, live_enabled)
        with st.spinner("Evaluating the ticket…"):
            result = evaluate(message, demo=demo, model=model)
        st.session_state.evaluation = {"message": message, "mode": mode, "result": result}
    except SupportError as error:
        st.error(str(error))

saved = st.session_state.get("evaluation")
if saved and saved["message"] == message and saved["mode"] == mode:
    result = saved["result"]
    analysis, decision = result["analysis"], result["decision"]
    st.subheader(decision["status"])
    st.write("**Recommended team:**", analysis["department"].title())
    st.write("**Priority:**", decision["priority"])
    st.write("**Tone guidance:**", decision["tone_guidance"])
    for reason in decision["review_reasons"]:
        st.warning(reason)
    st.subheader("What the evaluation returned")
    st.write(f"Selected-team probability: {analysis['department_probability']:.1%}")
    st.write(f"Choice confidence: {analysis['department_confidence']:.2f} (a separate distribution summary)")
    st.write(f"Frustration position: {analysis['frustration']:.2f} on the 0–2 rubric")
    st.write(f"Urgency probability: {analysis['is_urgent']:.1%}")
    st.write(f"Needs-clarification probability: {analysis['needs_clarification']:.1%}")
    st.bar_chart(analysis["department_probabilities"])
    st.subheader("Suggested customer reply")
    st.write(decision["suggested_reply"])
    st.caption("This draft comes from editable Python application templates. Review it before sending. The app sends no replies or refunds.")
    st.caption(f"{result['mode']} · Model: {result['model']} · Evaluation time: {result['elapsed_seconds']} seconds")
    with st.expander("Response data"):
        st.json(result["raw_response"])
elif saved:
    st.info("The input or mode changed. Submit again to evaluate the current ticket.")

with st.expander("Playground request for the current message"):
    try:
        st.json(make_request(message, model))
    except SupportError:
        st.write("Enter a message to see its request.")
st.caption("Course thresholds are illustrative. This app keeps no ticket database; browser refresh clears session results.")

# Jev Support Course Deployment

This is the Module 7 deployment copy of the customer support assistant. It recommends teams, flags urgency, and selects template replies for human review. It never sends replies or refunds. Demo results are invented fixtures.

Run locally from this folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Deploy the contents of this folder at your repository root, with entrypoint `app.py` and `requirements.txt` alongside it. Choose Python 3.13 in the host settings when available. Start without secrets to verify Demo mode.

Live mode is disabled unless `ENABLE_LIVE` is true. For a controlled live class, store root-level TOML values in the host Secrets settings:

```toml
ENABLE_LIVE = true
TYPESAFE_API_KEY = "your-actual-key"
TYPESAFE_MODEL = "jev-latest"
```

Environment values take precedence over `st.secrets`. Locally, an ignored `.streamlit/secrets.toml` can hold these values. `secrets.example.toml` is only a placeholder template and is not loaded automatically. Do not commit a real secret.

Public course deployments should remain demo-only. The enabled live interface uses the server's API key on behalf of any viewer who can reach it. Restrict app sharing for live practice. The five-second cooldown and ten-attempt cap are per Streamlit session and are not a global budget. A refresh, new session or restart may reset them. Use account-level controls where available and monitor usage separately.

To stop live access, set `ENABLE_LIVE = false`, remove the hosted key if appropriate, and restart the app. A CLI invocation of support.py is an instructor utility and does not use the web-interface gate. Do not expose that utility as a public command endpoint.

See the parent pack's technical guide and checklist for the full lesson. Runtime JSON files must stay beside support.py. No ticket database is created by this app. Live tickets are sent to TypeSafe; use the fictional examples when recording.

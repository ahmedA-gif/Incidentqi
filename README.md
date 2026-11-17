# IncidentIQ

IncidentIQ is a browser-based workspace for diagnosing infrastructure incidents. It uses the supplied `IncidentIQ-Final.owl` from Protégé, a FastAPI backend, and a LangGraph workflow with parallel diagnostic agents.

## Run on Windows

From the project directory in PowerShell, install Python 3.11 or later and put Java on `PATH` to run HermiT.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [IncidentIQ](http://127.0.0.1:8000/). The first run loads the database outage demo. Select the network or web service demo and run the diagnosis again to compare the evidence. The API reference is at [Swagger UI](http://127.0.0.1:8000/docs).

If Java is unavailable, the app uses RDFLib property paths for dependency inference. The footer shows the active reasoning mode. You can edit the domain model in Protégé, export it over `IncidentIQ-Final.owl`, and restart the server to load the changes.

## Investigate your project

1. Select **My project** and enter the affected service and symptom. The ontology covers the student portal, attendance and examination systems, authentication, database, and network services. Its modeled symptoms include HTTP 503, login failure, connection timeout, and slow response.
2. Optionally attach a ZIP up to 10 MB with project files. Include relevant `.log` files and dependency manifests such as `requirements.txt`, `pyproject.toml`, or `package.json`. IncidentIQ catalogs the ZIP, reads supported manifests, and shows recognized log markers with file and line references.
3. Optionally download the status template from the form, fill in your service observations and test results, and attach the JSON. Keep the exact ontology IDs and use `unknown` for missing observations. The app uses this snapshot for that run. A project run with no snapshot shows unknown statuses.
4. Run the diagnosis. Open candidate faults for test results and potential impact. Follow evidence IDs to the underlying ontology statement, status snapshot, or project file reference. Open **Agent activity** to see each agent's contribution.

ZIPs remain scoped to the current request. The app reads selected entries within size limits. It runs no uploaded code, production commands, network probes, or remediation. For this version, project logs provide context. The attached diagnostic test results determine which ontology candidates have direct test support.

## Agent workflow

1. **Supervisor** maps the report to known service and symptom IDs.
2. **Diagnosis**, **Reasoning**, **Monitoring**, and **Project** run in parallel. They gather candidate faults and modeled causes, resolve transitive dependencies, read the selected status snapshot, and inspect uploaded project evidence.
3. **Solution** waits for all four results. It prioritizes candidates supported by failed tests, surfaces passing tests for alternatives, and retrieves the ontology's recommended actions. If the evidence supports competing causes, the report leaves the cause unresolved.

## NVIDIA intake

Copy `.env.example` to `.env` and add your NVIDIA API key to `NVIDIA_API_KEY`. Restart the server, then enable **Use NVIDIA for intake** for the desired run. IncidentIQ sends the incident report and ontology entity names to NVIDIA. Uploaded files and status snapshots are processed locally. The model selects ontology IDs and the backend validates those IDs against the catalog. A failed provider request falls back to local matching and is shown in the report.

See the [NVIDIA NIM API reference](https://docs.api.nvidia.com/nim/reference/llm-apis), [LangGraph workflow documentation](https://docs.langchain.com/oss/python/langgraph/workflows-agents), and [Owlready2 reasoning documentation](https://owlready2.readthedocs.io/en/latest/reasoning.html).

## Deploy on Vercel

Import the GitHub repository as a FastAPI project with the repository root as its root directory. Vercel detects the `app` entry point in `app.py` and uses Python 3.12. The deployment uses RDFLib for reasoning when Java is unavailable. The hosted ZIP limit is 4 MB to leave room for the optional JSON snapshot and multipart overhead. See the [FastAPI deployment guide](https://vercel.com/docs/frameworks/backend/fastapi) and [Vercel Function limits](https://vercel.com/docs/functions/limitations#request-body-size).

For NVIDIA intake, create a sensitive `NVIDIA_API_KEY` environment variable in the intended Vercel environment and redeploy. Use a protected deployment for shared-key testing, since anyone with access to the diagnosis endpoint can use the configured key through the app. See [NVIDIA key setup](https://docs.api.nvidia.com/nim/re/docs/api-quickstart) and [Vercel environment variables](https://vercel.com/docs/environment-variables).

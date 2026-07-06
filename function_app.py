import json
import logging
import os
import re

import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ---------------------------------------------------------------------------
# Shared helpers (identical logic to main.py)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Du bist ein Assistent, der aus einer freien Kundenanfrage eine strukturierte "
    "Leistungsbeschreibung erstellt. Gib deine Antwort ausschließlich als gültiges JSON-Objekt "
    "mit den Feldern 'titel' (string), 'scope' (string), 'aufwand' (string) und "
    "'rollen' (array of strings) zurück – kein Markdown, kein Fließtext drumherum."
)

_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Kundenanfrage analysieren</title>
</head>
<body style="font-family: system-ui, sans-serif; background: #f0f2f5; margin: 0; padding: 2rem 1rem;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <h1 style="font-size: 1.4rem; margin: 0 0 1.5rem; color: #1a1a1a;">Kundenanfrage analysieren</h1>
        <form id="analyzeForm">
            <label for="customer_request" style="font-size: 0.9rem; font-weight: 600; color: #333;">Kundenanfrage</label>
            <textarea
                id="customer_request"
                name="customer_request"
                placeholder="Gib hier die Kundenanfrage ein …"
                required
                style="display: block; width: 100%; height: 140px; margin-top: 0.5rem; padding: 0.6rem 0.75rem; font-size: 1rem; font-family: inherit; border: 1px solid #ccc; border-radius: 4px; resize: vertical; box-sizing: border-box;"
            ></textarea>
            <button
                type="submit"
                style="margin-top: 1rem; padding: 0.55rem 1.4rem; font-size: 1rem; font-family: inherit; background: #0066cc; color: #fff; border: none; border-radius: 4px; cursor: pointer;"
                onmouseover="this.style.background='#0052a3'"
                onmouseout="this.style.background='#0066cc'"
            >Analysieren</button>
        </form>
        <div id="result" style="display: none; margin-top: 1.5rem;"></div>
    </div>
    <script>
        function renderTable(data) {
            const rows = [
                ["Titel",   data.titel   ?? "\\u2013"],
                ["Scope",   data.scope   ?? "\\u2013"],
                ["Aufwand", data.aufwand ?? "\\u2013"],
                ["Rollen",  Array.isArray(data.rollen) ? data.rollen.join(", ") : (data.rollen ?? "\\u2013")],
            ];
            const tdBase = "padding: 0.55rem 0.75rem; vertical-align: top; border-bottom: 1px solid #e0e0e0;";
            const bodyRows = rows.map(([label, value]) => `
                <tr>
                    <td style="${tdBase} font-weight: 600; width: 30%; color: #555; white-space: nowrap;">${label}</td>
                    <td style="${tdBase} color: #1a1a1a;">${value}</td>
                </tr>`).join("");
            return `<table style="width:100%;border-collapse:collapse;font-size:0.9rem;"><tbody>${bodyRows}</tbody></table>`;
        }

        document.getElementById("analyzeForm").addEventListener("submit", async (e) => {
            e.preventDefault();
            const text = document.getElementById("customer_request").value;
            const resultBox = document.getElementById("result");
            resultBox.style.display = "none";
            resultBox.innerHTML = "";

            const response = await fetch(window.location.pathname, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ customer_request: text }),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: response.statusText }));
                resultBox.style.display = "block";
                resultBox.innerHTML = `<p style="color:#c0392b;font-size:0.9rem;">Fehler: ${err.detail ?? response.statusText}</p>`;
                return;
            }

            const data = await response.json();
            resultBox.style.display = "block";
            resultBox.innerHTML = renderTable(data);
        });
    </script>
</body>
</html>"""

_project_client: AIProjectClient | None = None


def _get_project_client() -> AIProjectClient:
    global _project_client
    if _project_client is None:
        endpoint = os.environ.get("AZURE_FOUNDRY_PROJECT_ENDPOINT")
        if not endpoint:
            raise RuntimeError(
                "Umgebungsvariable AZURE_FOUNDRY_PROJECT_ENDPOINT ist nicht gesetzt."
            )
        _project_client = AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
    return _project_client


def _parse_json_response(raw: str) -> dict:
    """Strip optional Markdown code fences and parse JSON."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return json.loads(cleaned)


def _json_response(data: dict | list, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(data, ensure_ascii=False),
        mimetype="application/json",
        status_code=status,
    )


# ---------------------------------------------------------------------------
# HTTP Trigger – GET returns the HTML form, POST runs the analysis
# ---------------------------------------------------------------------------

@app.route(route="analyze", methods=["GET", "POST"])
def analyze_http(req: func.HttpRequest) -> func.HttpResponse:

    # ── GET ──────────────────────────────────────────────────────────────────
    if req.method == "GET":
        return func.HttpResponse(_HTML, mimetype="text/html", status_code=200)

    # ── POST ─────────────────────────────────────────────────────────────────
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"detail": "Ungültiges JSON im Request-Body."}, 400)

    customer_request = (body.get("customer_request") or "").strip()
    if not customer_request:
        return _json_response(
            {"detail": "Feld 'customer_request' fehlt oder ist leer."}, 400
        )

    deployment = os.environ.get("AZURE_FOUNDRY_MODEL_DEPLOYMENT")
    if not deployment:
        return _json_response(
            {"detail": "Umgebungsvariable AZURE_FOUNDRY_MODEL_DEPLOYMENT ist nicht gesetzt."}, 500
        )

    try:
        client = _get_project_client()
        openai_client = client.get_openai_client()
        response = openai_client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": customer_request},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError as exc:
        return _json_response({"detail": str(exc)}, 500)
    except Exception as exc:
        logging.error("Foundry-Fehler: %s", exc, exc_info=True)
        return _json_response(
            {"detail": f"Fehler beim Aufruf von Azure Foundry: {exc}"}, 502
        )

    raw = response.choices[0].message.content
    try:
        return _json_response(_parse_json_response(raw))
    except json.JSONDecodeError as exc:
        return _json_response(
            {"detail": f"Modell hat kein gültiges JSON zurückgegeben ({exc}): {raw!r}"}, 502
        )

import json
import os

from dotenv import load_dotenv
load_dotenv()  # lädt .env aus dem Arbeitsverzeichnis

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import re


def _parse_json_response(raw: str) -> dict:
    """Strip optional Markdown code fences and parse JSON."""
    # Remove ```json ... ``` or ``` ... ``` wrappers the model sometimes adds.
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return json.loads(cleaned)


SYSTEM_PROMPT = (
    "Du bist ein Assistent, der aus einer freien Kundenanfrage eine strukturierte "
    "Leistungsbeschreibung erstellt. Gib deine Antwort ausschließlich als gültiges JSON-Objekt "
    "mit den Feldern 'titel' (string), 'scope' (string), 'aufwand' (string) und "
    "'rollen' (array of strings) zurück – kein Markdown, kein Fließtext drumherum."
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# Module-level client – instantiated once on first request to respect env var loading order.
_project_client: AIProjectClient | None = None


def _get_project_client() -> AIProjectClient:
    global _project_client
    if _project_client is None:
        endpoint = os.environ.get("AZURE_FOUNDRY_PROJECT_ENDPOINT")
        if not endpoint:
            raise RuntimeError("Umgebungsvariable AZURE_FOUNDRY_PROJECT_ENDPOINT ist nicht gesetzt.")
        _project_client = AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
    return _project_client


class AnalyzeRequest(BaseModel):
    customer_request: str


class AnalyzeResponse(BaseModel):
    titel: str
    scope: str
    aufwand: str
    rollen: list[str]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest):
    deployment = os.environ.get("AZURE_FOUNDRY_MODEL_DEPLOYMENT")
    if not deployment:
        raise HTTPException(
            status_code=500,
            detail="Umgebungsvariable AZURE_FOUNDRY_MODEL_DEPLOYMENT ist nicht gesetzt.",
        )

    try:
        client = _get_project_client()
        openai_client = client.get_openai_client()

        response = openai_client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": body.customer_request},
            ],
            response_format={"type": "json_object"},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fehler beim Aufruf von Azure Foundry: {exc}")

    raw = response.choices[0].message.content

    try:
        return _parse_json_response(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Modell hat kein gültiges JSON zurückgegeben ({exc}): {raw!r}",
        )

# vibe-coding-webinar

enthält alle Inhalte für das 50-minütige Live-Webinar 'Vibe Coding mit GitHub Copilot'. Es richtet sich an ein Reseller-Publikum und zeigt, wie mit GitHub Copilot Agent Mode in kurzer Zeit ein produktionsreifer Prototyp entsteht – von FastAPI bis zur Azure Function mit Microsoft Foundry-Anbindung.

## Ablauf

● Eingabe: Kunde beschreibt Bedarf in Freitext (z.B. 'Wir brauchen eine Migration von 200 VMs nach Azure inkl. Backup-Konzept')
● Copilot Agent Mode baut live: FastAPI-Route + HTML-Frontend mit Text Area
● Microsoft Foundry-Modell strukturiert die Anfrage (Titel, Scope, Aufwand, Rollen)
● Umbau der FastAPI-App zur Azure Function – live per Prompt
● Deployment als Serverless-Ressource in Azure

## Warum dieser Use-Case für Reseller?

● Direkter Bezug zum realen Vertriebsprozess (Angebots-/SOW-Erstellung)
● Zeigt, dass mit wenig Custom-Code echte interne Tools entstehen
● Foundry-Konsum und Serverless-Compute nutzungsbasiert – passt zum CSP/NCE-Pricing
● Direkt als Partner-Demo oder Accelerate-PoC positionierbar

## Die Prompts

### Grundgerüst-Prompt

Erstelle eine FastAPI-App mit folgender Struktur:
- Ein POST-Endpoint /Analyze, der ein JSON mit dem Feld 'customer_request' 
  (Freitext) entgegennimmt
- Ein HTML-Formular unter '/' mit Textarea und Submit-Button
- Response von /analyze vorerst nur den Text als JSON zurückgeben (Platzhalter)
- Nutze Jinja2Templates für das HTML
- CORS für lokale Entwicklung erlauben

### Optimierungs-Prompt

Style das Formular mit CSS-Basics (zentriert, max-width 600px, Padding).
Kein Framework, nur inline CSS.

### Foundry-Prompt

Erweitere /analyze: Text an Microsoft Foundry (New) senden.
Nutze azure-ai-projects SDK (Python 2.x) mit Project-Endpoint,
NICHT Connection-String oder Hub-basierte Projekte.
Erstelle eine .env Datei und füge python-dotenv zu requirements.txt hinzu.

Nutze bitte die .env Datei, um die Umgebungsvariablen zu lesen:
AZURE_FOUNDRY_PROJECT_ENDPOINT, AZURE_FOUNDRY_MODEL_DEPLOYMENT
Nutze DefaultAzureCredential (kein statischer API-Key).
System-Prompt: 'Du bist ein Assistent, der aus einer freien Kundenanfrage
eine strukturierte Leistungsbeschreibung mit Titel, Scope, geschätztem
Aufwand und benötigten Rollen erstellt. Antworte als JSON.'
Strukturierte Antwort im Response zurückgeben.

### robustes JSON Parsing

Das Modell liefert manchmal Markdown-Codeblöcke um das JSON.
Robuste Parsing-Funktion bauen: Backticks entfernen, Fehler abfangen.

### Frontend verbessern

Antwort nicht als rohes JSON, sondern als Tabelle anzeigen:
Felder Titel, Scope, Aufwand, Rollen.


### Switch zu Azure Function App

Wandle diese FastAPI-App in eine Azure Function (Python v2, HTTP Trigger) um.
Behalte die komplette Logik inkl. Foundry-Anbindung bei. Erstelle:
- function_app.py mit HTTP-Trigger
- requirements.txt
- host.json und local.settings.json 
- Übernimm dabei die Settings aus der .env in der local.settings.json
- HTML-Formular als statische GET-Response im selben Trigger
- Fass beide Methoden in der HTTP-only Function Apps mit Formular + API (GET/POST) in einem Handler auf einer expliziten Route zusammenfassen, damit route=““ NICHT =functionname 
- Setze in local.settings.json den Wert "AzureWebJobsStorage": ""
  Um den Azurite Emulator auszuschalten
- gitignore Datei um keine Secrets zu veröffentlichen

### Validierung

Sicherstellen, dass die Foundry-Integration unverändert übernommen wurde –
insbesondere die Env-Variablen-Namen prüfen.

### Deployment Vorbereitung

Exakte Azure CLI Befehle erstellen, um diese Function App unter
[NAME] in Resource Group [RG]
zu deployen,
inklusive App Settings für AZURE_FOUNDRY_PROJECT_ENDPOINT
und AZURE_FOUNDRY_MODEL_DEPLOYMENT.

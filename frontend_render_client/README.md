# AI Trip Planner Frontend

This directory contains the Flask web client for the AI Trip Planner. It provides the browser interface for creating, refining, translating, evaluating, and downloading travel itineraries. AI and external data processing are handled by a separate FastAPI backend.

The frontend can run locally while connecting to a backend deployed on Render, or it can be served through Passenger/WSGI hosting.

## Features

- Generate a day-by-day itinerary from departure city, destination, and dates.
- Refine the latest plan with preset preferences or custom instructions.
- Preserve the original plan when a refined plan is generated.
- Display coverage scores for relevance, trip alignment, locations, dates, completeness, budget detail, and daily structure.
- Translate itinerary text into supported languages and optionally play generated audio.
- Request travel insurance quotes through the backend.
- Download the current plans and evaluation metrics as a formatted `.docx` file.
- Keep generated plans in a local SQLite database so they survive a normal Flask process restart.
- Emit JSON-lines logs suitable for collecting alongside backend logs.

## Architecture

```text
Browser
	|
	v
Flask frontend (this directory)
	|
	+-- POST /query       -> FastAPI backend
	+-- POST /translate   -> FastAPI backend
	+-- POST /insurance   -> FastAPI backend
	|
	+-- SQLite: plans.db
	+-- Generated audio: static/audio_*.mp3
```

The frontend does not contain the AI agents or backend tools. `FASTAPI_BASE_URL` determines which backend receives requests.

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | Flask application, routes, backend calls, plan storage, scoring, and DOCX generation |
| `plan_evaluation.py` | Shared deterministic coverage evaluator, also used by the root Flask app |
| `templates/index.html` | Main user interface and browser-side interactions |
| `static/` | CSS/JavaScript assets and generated translation audio files |
| `requirements.txt` | Python dependencies |
| `.env.example` | Configuration template; copy this to `.env` |
| `passenger_wsgi.py` | WSGI entry point for Passenger hosting |
| `run_frontend_remote.bat` | Windows setup and startup script |
| `plans.db` | Runtime SQLite database, created automatically |

## Requirements

- Windows, Linux, or macOS
- Python 3.10 or newer recommended
- A reachable AI Trip Planner FastAPI backend
- Network access to install Python packages and call the backend

## Configuration

Create a `.env` file in this directory. Do not commit it, because it contains the Flask session secret.

```env
FASTAPI_BASE_URL=https://trip-planner-v2-0-4.onrender.com
FLASK_SECRET_KEY=replace-with-a-random-secret
```

Generate a strong secret with:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

### Environment variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `FASTAPI_BASE_URL` | Yes | None | Base URL of the FastAPI backend, without a trailing route such as `/query` |
| `FLASK_SECRET_KEY` | Yes | None | Secret used to sign Flask sessions |
| `PLAN_TTL_SECONDS` | No | `86400` | Lifetime of stored plans before cleanup |
| `AUDIO_TTL_SECONDS` | No | `3600` | Lifetime of generated MP3 files before cleanup |
| `QUERY_TIMEOUT_SECONDS` | No | `240` | Timeout for itinerary generation/refinement requests |
| `REFINEMENT_PLAN_MAX_CHARS` | No | `6000` | Maximum existing-plan context sent during refinement |
| `RESET_PLANS_ON_START` | No | `true` | Clears all rows in `plans.db` when the app starts |
| `FLASK_DEBUG` | No | `false` | Enables Flask debug mode for local development only |
| `LOG_LEVEL` | No | `INFO` | Logging level, for example `DEBUG`, `INFO`, or `WARNING` |

`RESET_PLANS_ON_START=true` is convenient for a clean local session, but set it to `false` when stored plans must survive application restarts.

## Windows quick start

The easiest option is to double-click `run_frontend_remote.bat` from File Explorer. The script:

1. Changes into the frontend directory.
2. Creates `.venv` if it does not exist.
3. Activates `.venv`.
4. Installs or updates packages from `requirements.txt`.
5. Starts `app.py` on `http://127.0.0.1:5000`.

Keep the command window open while using the application. Press `Ctrl+C` in that window to stop the server.

## Manual setup

From this directory, run:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

On Linux or macOS, activate the environment with:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The application fails fast at startup if either required environment variable is missing.

## User workflow

1. Enter the departure city, destination city, departure date, and return date.
2. Submit the form to send an automatically constructed itinerary request to the backend.
3. Review the generated plan, agent status, and evaluation scores.
4. Use a preset refinement option or enter custom refinement instructions.
5. Translate visible itinerary content when needed.
6. Request insurance quotes using the trip details, age, and coverage type.
7. Download the plans and scores as a Word document.
8. Use the clear action to remove the current browser session and start a new trip.

The backend may be asleep on Render's free tier. The frontend allows a long request timeout and retries transient timeout or connection failures once.

## Coverage metrics

Newly generated or refined drafts use the same evaluator in both frontend deployments:

- Relevance combines trip alignment, day coverage and requested topic coverage. It is not a semantic or factual judgment.
- Trip alignment checks complete city names and both full travel dates. A matching year alone earns no date credit.
- Dates support ISO, day/month/year and named-month forms, including ordinal days such as `6th November 2026`. Include the year explicitly.
- Completeness checks numbered trip days and activities, meals, lodging, transport, practical information and a priced budget, rather than word count.
- Budget detail checks currency-labelled amounts, priced categories, a trip total, costing basis and estimate disclosure. An identifiable single-currency subtotal mismatch reduces credit; other arithmetic is not certified.
- Daily structure checks unique `Day N` sections and multiple distinct time slots with activities. Missing or duplicate days reduce credit.
- Overall coverage equally weights relevance, alignment, completeness, budget detail and daily structure, so missing dates and budget details affect the result.

These are coverage signals, not verification of market prices, route feasibility, source freshness, preference compliance or factual accuracy. Live data still depends on backend tools and their cited sources. Previously saved scores remain unchanged until a plan is regenerated or refined.

Include `plan_evaluation.py` when deploying this directory independently. From the repository root, run `python -m pytest tests/test_plan_evaluation.py -q` to validate scoring and both frontend reports.

## Frontend routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/` | Show the UI or generate a new itinerary |
| `POST` | `/refine` | Generate and append a refined version of the current itinerary |
| `GET` | `/clear` | Clear the current Flask session |
| `POST` | `/translate` | Proxy translation and save returned audio under `static/` |
| `POST` | `/insurance` | Proxy Squaremouth insurance quote requests |
| `POST` | `/download` | Return a formatted Word document containing the plans |

## Backend contract

The configured backend must expose these endpoints:

- `POST /query` with `question` and `chat_history`; returns an `answer` and optionally `agents_used` and `agent_status`.
- `POST /translate` with `text` and `target_language`; returns `translated_text` and optionally an `audio_bytes` list.
- `POST /insurance/squaremouth` with destination, dates, age, traveler count, and coverage type; returns insurance plans.

The frontend adds `FASTAPI_BASE_URL` to each route, so a backend base URL such as `https://example.com` becomes `https://example.com/query`.

## Data and generated files

- `plans.db` is created beside `app.py`. It stores plans as JSON keyed by a UUID held in the Flask session.
- Expired plans are removed when the database is accessed, based on `PLAN_TTL_SECONDS`.
- Translation audio is written to `static/audio_*.mp3` and old files are removed when a new audio file is created.
- The generated Word document is streamed directly to the browser and is not stored permanently by the frontend.

Runtime files such as `.venv/`, `.env`, `plans.db`, and generated audio should normally be excluded from source control.

## Passenger deployment

Passenger-compatible hosting should use `passenger_wsgi.py` as the WSGI entry point. It imports the Flask application as:

```python
from app import app as application
```

Set the required environment variables in the hosting provider's configuration, install `requirements.txt`, and ensure the application directory is writable so SQLite and generated audio can be created.

Do not enable `FLASK_DEBUG` on a publicly reachable deployment. Restart the application after changing environment variables.

## Troubleshooting

### `FLASK_SECRET_KEY is not set`

Create `.env` beside `app.py` and add `FLASK_SECRET_KEY`.

### `FASTAPI_BASE_URL is not set`

Add the backend URL to `.env`, then restart the Flask process.

### Backend timeout or connection error

Confirm the backend URL is reachable and that its service is running. A Render service may need time to wake up after inactivity. Increase `QUERY_TIMEOUT_SECONDS` only when the backend genuinely needs more time.

### No plan is available for refinement or download

Generate a plan first in the same browser session. Also check whether the application is restarting with `RESET_PLANS_ON_START=true`.

### Port 5000 is already in use

Stop the other Flask process, or run the app on another port by changing the `app.run` call for local development.

## Development notes

- Use the project virtual environment when installing dependencies or running the app.
- Keep `.env` secrets out of commits and screenshots.
- Review JSON-lines logs for request failures and backend timing information.
- The frontend currently has no automated test suite; validate changes by starting the app and exercising generation, refinement, translation, insurance, and download flows against a working backend.

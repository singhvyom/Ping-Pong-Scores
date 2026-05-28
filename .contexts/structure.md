# PingPong Codebase Structure

This repo is a small Python + React app that reads ping pong match results from a Google Sheet, computes summary statistics, and displays them in a simple frontend.

## High-level Architecture

Data flows in this order:

1. [`backend/main.py`](../backend/main.py) fetches raw sheet rows using a Google service account.
2. `pandas` converts rows into a DataFrame and computes summary statistics for each player.
3. [`backend/app.py`](../backend/app.py) exposes those statistics via a Flask endpoint (`GET /`).
4. [`frontend/src/App.jsx`](../frontend/src/App.jsx) fetches the JSON from Flask and renders the numbers.

## Backend (Python)

### Sheet fetch and stats computation (`backend/main.py`)

- Entry point: `fetch_data()`
- Authentication:
  - Uses `credentials.json` at the repo root with `google.oauth2.service_account.Credentials.from_service_account_file(...)`.
  - Authorizes `gspread` with the Sheets scope `https://www.googleapis.com/auth/spreadsheets`.
- Sheet selection:
  - Opens the spreadsheet by key in `backend/main.py` via `gspread` (`open_by_key`); the actual ID is only in source, not repeated in this doc.
  - Reads the default worksheet via `sheet.sheet1.get_all_values()`.
- Data shaping:
  - Converts sheet rows into a DataFrame:
    - `scores = pd.DataFrame(values_list[1:], columns=values_list[0])`
  - Casts expected columns to integers:
    - `scores['H'] = scores['H'].astype(int)`
    - `scores['V'] = scores['V'].astype(int)`
  - Drops rows with missing values: `scores = scores.dropna()`
- Statistics:
  - Win/loss record (count of games where one player’s score is greater than the other):
    - `H.win_loss_record = int((scores['H'] > scores['V']).sum())`
    - `Vyom.win_loss_record = int((scores['V'] > scores['H']).sum())`
  - Other summary fields computed from the relevant score column:
    - `average` (mean)
    - `std_deviation` (sample standard deviation via pandas `.std()`)
    - `max`
    - `min`
- Return value:
  - A nested dict (JSON-serializable) structured by player keys `H` and `Vyom`.

### API server (`app.py`)

- Flask app with CORS enabled:
  - `CORS(app)`
- Endpoint:
  - `GET /`
  - Calls `main.fetch_data()` and returns the stats as JSON: `return jsonify(stats)`

## Data Model / JSON Shape

The Flask `GET /` endpoint returns an object shaped like:

```json
{
  "H": {
    "win_loss_record": 0,
    "average": 0.0,
    "std_deviation": 0.0,
    "max": 0,
    "min": 0
  },
  "Vyom": {
    "win_loss_record": 0,
    "average": 0.0,
    "std_deviation": 0.0,
    "max": 0,
    "min": 0
  }
}
```

The JSON keys are driven by the sheet columns `H` and `V` in `backend/main.py` (with the `V` column mapped to `Vyom` in the returned JSON).

## Frontend (React)

### Vite + React entrypoints

- Vite config: [`frontend/vite.config.js`](../frontend/vite.config.js)
- React root rendering: [`frontend/src/main.jsx`](../frontend/src/main.jsx)

### App rendering and data fetching (`App.jsx`)

- On mount (`useEffect`), the app calls `fetchScores()`.
- It fetches from:
  - `http://127.0.0.1:5000`
- It expects the response to be the JSON object described in the “Data Model / JSON Shape” section.
- It renders:
  - An “H Statistics” section based on `data.H`
  - A “Vyom Statistics” section based on `data.Vyom`

Note: there is no frontend dev-server proxy configured; the frontend fetches the Flask server directly (so both servers must be running during development).

## Local Development / Runbook

### 1) Backend (Flask)

From the repo root:

```bash
python backend/app.py
```

This serves `GET /` on the default Flask development address (typically `http://127.0.0.1:5000/`).

### 2) Frontend (Vite)

From the repo root:

```bash
cd frontend
npm install
npm run dev
```

Vite typically runs on `http://localhost:5173/`.

### 3) Live VAD score harness

The live voice Phase 0 harness uses the laptop/default microphone, WebRTC VAD,
Whisper, and the shared `GameState` rules engine.

From the repo root:

```bash
python backend/scripts/live_score_vad.py --list-devices
python backend/scripts/live_score_vad.py --first-server h --debug-vad
python backend/scripts/live_score_vad.py --first-server h --model tiny
```

Useful tuning flags:

- `--device`: choose a specific PortAudio device id/name from `--list-devices`.
- `--vad-mode`: WebRTC aggressiveness, `0` least aggressive through `3` most aggressive.
- `--end-silence-ms`: trailing silence required before a speech chunk is closed.
- `--max-segment-ms`: maximum chunk duration before forcing transcription.
- `--max-inferred-gap`: max points to infer from a single recognized phrase; default is conservative (`1`).

Outputs:

- GT-shaped predicted rows: `data/runs/live_<timestamp>_predicted.txt` by default.
- Recognized transcript phrases: `data/transcripts/live_<timestamp>.txt` by default.

The output table is compatible with:

```bash
python backend/scripts/compare_score_tables.py data/runs/live_<timestamp>_predicted.txt data/game_gt/game1_gt.txt
```

## Dependencies

### Backend dependencies (based on imports)

- `flask`
- `flask-cors`
- `gspread`
- `pandas`
- `google-auth` (used via `google.oauth2.service_account`)
- `openai-whisper` (batch transcription and live chunk transcription)
- `sounddevice` (local microphone capture for the live VAD harness)
- `webrtcvad-wheels` (WebRTC speech activity detection)

### Frontend dependencies (based on `frontend/package.json`)

- `react`
- `react-dom`
- `vite`
- `@vitejs/plugin-react`

## Security Note

`credentials.json` at the repo root holds the Google service account private key used by `backend/main.py`.

Do not commit or share this file outside your environment.

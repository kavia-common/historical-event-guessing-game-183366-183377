Historical Event Trivia - Multi-Container Integration Guide

Overview
This repository contains three cooperating parts:
- Database (PostgreSQL): stores events, clues, and game sessions
- Backend (Flask API): game logic and sessions, connects to Postgres
- Frontend (React): user interface, calls backend API

Environment Variable Alignment
- Database (defaults from database/startup.sh):
  POSTGRES_HOST=localhost
  POSTGRES_PORT=5000
  POSTGRES_DB=myapp
  POSTGRES_USER=appuser
  POSTGRES_PASSWORD=dbuser123
  DATABASE_URL=postgresql://appuser:dbuser123@localhost:5000/myapp

- Backend (historical-event-guessing-game-183366-183377/backend/backend.env.example):
  PORT=3001
  HOST=0.0.0.0
  DATABASE_URL=postgresql://appuser:dbuser123@localhost:5000/myapp
  # or via individual POSTGRES_* variables above
  CORS_ALLOWED_ORIGINS=http://localhost:3000
  COOKIE_SECURE=false
  COOKIE_SAMESITE=Lax
  COOKIE_MAX_AGE=604800

- Frontend (historical_event_trivia_frontend/.env.example):
  REACT_APP_API_BASE=http://localhost:3001

CORS and Cookies
- The frontend fetch layer uses credentials: 'include' so cookies are sent and received.
- Backend sets an HttpOnly cookie named session_id.
- To allow cross-origin cookies:
  - Ensure the browser origin is allowed in CORS_ALLOWED_ORIGINS (e.g., http://localhost:3000).
  - The backend should enable CORS with credentials and reflect allowed origins.
  - SameSite=Lax allows typical navigation/usage; for strict cross-site embedding you may need SameSite=None and COOKIE_SECURE=true (HTTPS required).
- For local development:
  - Keep COOKIE_SECURE=false.
  - Keep COOKIE_SAMESITE=Lax.
  - Ensure REACT_APP_API_BASE matches the backend origin (http://localhost:3001).

Startup Sequence (Local)
1) Start the database:
   - cd historical-event-guessing-game-183366-183375/historical_event_trivia_database
   - ./startup.sh
   This creates the database and seeds data. Connection string saved in db_connection.txt.

2) Start the backend:
   - cd historical-event-guessing-game-183366-183377/backend
   - cp backend.env.example .env   # adjust if needed
   - export $(grep -v '^#' .env | xargs)  # or use a loader; Flask uses dotenv if installed
   - python run.py
   The API will bind to http://localhost:3001 if PORT is set to 3001.

3) Start the frontend:
   - cd historical-event-guessing-game-183366-183376/historical_event_trivia_frontend
   - cp .env.example .env   # adjust REACT_APP_API_BASE if your backend is different
   - npm install
   - npm start
   The frontend will run on http://localhost:3000 and call the backend at REACT_APP_API_BASE.

Verification Steps
- Health check:
  - GET http://localhost:3001/ should return { "message": "Healthy" }
- OpenAPI (if enabled):
  - http://localhost:3001/docs/
- Game flow via frontend:
  - Open http://localhost:3000
  - The app should load today’s game. Clicking “Reveal Next Clue” should reveal clues progressively.
  - Submit guesses. After up to 5 attempts, the game ends and shows answer payload.
- Game flow via API:
  - GET  http://localhost:3001/api/today
  - POST http://localhost:3001/api/reveal with credentials
  - POST http://localhost:3001/api/guess { "guess": "..." } with credentials

Notes
- If running over HTTPS for production, set COOKIE_SECURE=true and consider COOKIE_SAMESITE=None for cross-site scenarios.
- Update CORS_ALLOWED_ORIGINS to your deployed frontend origin(s).

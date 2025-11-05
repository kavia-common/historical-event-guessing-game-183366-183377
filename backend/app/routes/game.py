from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import re
import uuid

from flask import request, make_response
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields, validate
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Event, Clue, GameSession

# Constants for gameplay
MAX_CLUES = 5
MAX_ATTEMPTS = 5
SESSION_COOKIE_NAME = "session_id"

blp = Blueprint(
    "Game",
    "game",
    url_prefix="/api",
    description="Historical Event Trivia Game endpoints",
)


def _normalize_guess(text: str) -> str:
    """
    Normalize guesses: lowercase, remove non-alphanumerics except spaces, collapse whitespace.
    This makes matching more forgiving.
    """
    text = text.strip().lower()
    # Keep alphanumeric and spaces
    text = re.sub(r"[^a-z0-9\s]", "", text)
    # Collapse multiple whitespace to single spaces
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_title(title: str) -> str:
    """
    Normalize event title in the same way as guess normalization for comparison.
    """
    return _normalize_guess(title)


def _today_month_day() -> Tuple[int, int]:
    now = datetime.utcnow()
    return now.month, now.day


def _event_to_answer_payload(event: Event) -> Dict[str, Any]:
    return {
        "title": event.title,
        "year": event.year,
        "description": event.description,
    }


def _build_state_payload(
    session: GameSession,
    event: Event,
    clues: Optional[list[Clue]] = None,
    finished: bool = False,
) -> Dict[str, Any]:
    """
    Build the standard response payload fragment for game state.
    """
    payload: Dict[str, Any] = {
        "session_id": str(session.id),
        "date": f"{event.month:02d}-{event.day:02d}",
        "clues_revealed": session.clues_revealed,
        "max_clues": MAX_CLUES,
        "attempts_used": session.attempts_used,
        "max_attempts": MAX_ATTEMPTS,
        "game_over": session.is_completed,
        "success": session.is_success,
    }
    if finished and session.is_completed:
        payload["answer"] = _event_to_answer_payload(event)
    if clues is not None:
        # include the actually revealed clues text (up to clues_revealed)
        revealed_count = min(session.clues_revealed, len(clues))
        payload["clues"] = [c.text for c in sorted(clues, key=lambda x: x.order_index)][:revealed_count]
    return payload


def _get_or_create_session(
    db: Session, event: Event, incoming_session_id: Optional[str]
) -> Tuple[GameSession, bool]:
    """
    Retrieve an existing GameSession by incoming_session_id for today's event.
    If not present or mismatched event, create a new one.
    Returns (session, created_flag).
    """
    if incoming_session_id:
        try:
            sid = uuid.UUID(incoming_session_id)
        except Exception:
            sid = None
        if sid:
            existing = db.get(GameSession, sid)
            if existing and existing.event_id == event.id:
                return existing, False

    # Create a new session
    gs = GameSession(event_id=event.id)
    db.add(gs)
    db.flush()  # so gs.id is populated
    return gs, True


# Schemas for OpenAPI docs

class GuessInputSchema(Schema):
    session_id = fields.String(
        required=False,
        allow_none=True,
        description="Existing session ID to continue playing; if omitted, a new session is created or cookie is used",
    )
    guess = fields.String(
        required=True,
        validate=validate.Length(min=1),
        description="Player's guess for the historical event title",
    )


class RevealInputSchema(Schema):
    session_id = fields.String(
        required=False,
        allow_none=True,
        description="Existing session ID to continue playing; if omitted, a new session is created or cookie is used",
    )


class GameStateSchema(Schema):
    session_id = fields.String(required=True, description="Unique ID for the game session")
    date = fields.String(required=True, description="Month-Day of the event, format MM-DD")
    clues_revealed = fields.Integer(required=True, description="Number of clues revealed so far")
    max_clues = fields.Integer(required=True, description="Maximum number of clues available")
    attempts_used = fields.Integer(required=True, description="Number of guess attempts used")
    max_attempts = fields.Integer(required=True, description="Maximum guess attempts allowed")
    game_over = fields.Boolean(required=True, description="Whether the game is completed")
    success = fields.Boolean(required=True, description="Whether the game has been successfully completed")
    clues = fields.List(fields.String(), required=False, description="List of revealed clue texts in order")
    answer = fields.Dict(
        keys=fields.String(), values=fields.Raw(), required=False, description="Revealed at end: {title, year, description}"
    )


def _get_todays_event(db: Session) -> Optional[Event]:
    month, day = _today_month_day()
    stmt = select(Event).where(Event.month == month, Event.day == day).limit(1)
    return db.scalars(stmt).first()


def _get_event_clues(db: Session, event_id: int) -> list[Clue]:
    stmt = select(Clue).where(Clue.event_id == event_id)
    return list(db.scalars(stmt).all())


@blp.route("/today")
class TodayResource:
    """
    Get or create a game session for today's event and return current state with any revealed clues.
    """

    @blp.response(200, GameStateSchema)
    @blp.doc(
        summary="Get today's game state",
        description="Returns the current game state for today's event. Creates a session if none exists. "
                    "Session is persisted via HttpOnly cookie or provided session_id.",
        tags=["Game"],
    )
    def get(self):
        incoming_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        with session_scope() as db:
            event = _get_todays_event(db)
            if not event:
                abort(404, message="No event configured for today")

            session, created = _get_or_create_session(db, event, incoming_session_id)
            clues = _get_event_clues(db, event.id)
            # Ensure clues_revealed does not exceed limits or available clues
            session.clues_revealed = min(session.clues_revealed, min(len(clues), MAX_CLUES))
            db.flush()

            payload = _build_state_payload(session, event, clues=clues, finished=session.is_completed)
            resp = make_response(payload, 200)
            # set cookie if new session was created or cookie missing/mismatch
            if created or (incoming_session_id != str(session.id)):
                resp.set_cookie(
                    SESSION_COOKIE_NAME,
                    str(session.id),
                    httponly=True,
                    samesite="Lax",
                    secure=False,  # set to True behind HTTPS
                    max_age=7 * 24 * 3600,
                    path="/",
                )
            return resp


@blp.route("/reveal")
class RevealResource:
    """
    Reveal the next clue. Enforces maximum of 5 clues.
    """

    @blp.arguments(RevealInputSchema, location="json", as_kwargs=True)
    @blp.response(200, GameStateSchema)
    @blp.doc(
        summary="Reveal next clue",
        description="Reveals the next clue for today's event. Creates a session if needed. "
                    "Returns the updated game state with revealed clues. Max 5 clues.",
        tags=["Game"],
    )
    def post(self, session_id: Optional[str] = None):
        cookie_sid = request.cookies.get(SESSION_COOKIE_NAME)
        incoming_session_id = session_id or cookie_sid

        with session_scope() as db:
            event = _get_todays_event(db)
            if not event:
                abort(404, message="No event configured for today")

            session, _ = _get_or_create_session(db, event, incoming_session_id)
            clues = _get_event_clues(db, event.id)
            total_available = min(len(clues), MAX_CLUES)

            if session.is_completed:
                # Already finished; just return state (include answer)
                payload = _build_state_payload(session, event, clues=clues, finished=True)
                resp = make_response(payload, 200)
                if not incoming_session_id or incoming_session_id != str(session.id):
                    resp.set_cookie(
                        SESSION_COOKIE_NAME,
                        str(session.id),
                        httponly=True,
                        samesite="Lax",
                        secure=False,
                        max_age=7 * 24 * 3600,
                        path="/",
                    )
                return resp

            if session.clues_revealed < total_available:
                session.clues_revealed += 1
            # Do not exceed limits
            session.clues_revealed = min(session.clues_revealed, total_available)
            db.flush()

            payload = _build_state_payload(session, event, clues=clues, finished=False)
            resp = make_response(payload, 200)
            if not incoming_session_id or incoming_session_id != str(session.id):
                resp.set_cookie(
                    SESSION_COOKIE_NAME,
                    str(session.id),
                    httponly=True,
                    samesite="Lax",
                    secure=False,
                    max_age=7 * 24 * 3600,
                    path="/",
                )
            return resp


@blp.route("/guess")
class GuessResource:
    """
    Submit a guess for today's event. Enforces maximum of 5 attempts and normalizes input for match.
    """

    @blp.arguments(GuessInputSchema, location="json", as_kwargs=True)
    @blp.response(200, GameStateSchema)
    @blp.doc(
        summary="Submit a guess",
        description="Submits a guess for today's event. Guess text is normalized for a lenient match. "
                    "You have up to 5 attempts. Returns updated game state. If the game ends, the answer is included.",
        tags=["Game"],
    )
    def post(self, guess: str, session_id: Optional[str] = None):
        if not guess or not guess.strip():
            abort(400, message="Guess must be provided")

        cookie_sid = request.cookies.get(SESSION_COOKIE_NAME)
        incoming_session_id = session_id or cookie_sid

        with session_scope() as db:
            event = _get_todays_event(db)
            if not event:
                abort(404, message="No event configured for today")

            session, _ = _get_or_create_session(db, event, incoming_session_id)

            # If already completed, return final state with answer
            if session.is_completed:
                payload = _build_state_payload(session, event, finished=True)
                resp = make_response(payload, 200)
                if not incoming_session_id or incoming_session_id != str(session.id):
                    resp.set_cookie(
                        SESSION_COOKIE_NAME,
                        str(session.id),
                        httponly=True,
                        samesite="Lax",
                        secure=False,
                        max_age=7 * 24 * 3600,
                        path="/",
                    )
                return resp

            # Enforce attempts limit
            if session.attempts_used >= MAX_ATTEMPTS:
                session.is_completed = True
                session.is_success = False
                db.flush()
                payload = _build_state_payload(session, event, finished=True)
                resp = make_response(payload, 200)
                if not incoming_session_id or incoming_session_id != str(session.id):
                    resp.set_cookie(
                        SESSION_COOKIE_NAME,
                        str(session.id),
                        httponly=True,
                        samesite="Lax",
                        secure=False,
                        max_age=7 * 24 * 3600,
                        path="/",
                    )
                return resp

            # Count this attempt
            session.attempts_used += 1

            normalized_guess = _normalize_guess(guess)
            normalized_title = _normalize_title(event.title)

            if normalized_guess == normalized_title:
                session.is_completed = True
                session.is_success = True
            else:
                # If reached max attempts after this try, mark game over
                if session.attempts_used >= MAX_ATTEMPTS:
                    session.is_completed = True
                    session.is_success = False

            db.flush()
            # Build payload; if completed include answer
            payload = _build_state_payload(session, event, finished=session.is_completed)

            resp = make_response(payload, 200)
            if not incoming_session_id or incoming_session_id != str(session.id):
                resp.set_cookie(
                    SESSION_COOKIE_NAME,
                    str(session.id),
                    httponly=True,
                    samesite="Lax",
                    secure=False,
                    max_age=7 * 24 * 3600,
                    path="/",
                )
            return resp

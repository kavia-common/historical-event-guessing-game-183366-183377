from datetime import datetime
import uuid

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .db import Base


class Event(Base):
    """
    Represents a historical event. Each event can have multiple associated clues.
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Month and day for the event occurrence (e.g., today's date)
    month = Column(Integer, nullable=False)  # 1-12
    day = Column(Integer, nullable=False)    # 1-31
    year = Column(Integer, nullable=True)    # Some events may not have an exact year
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Ensure that for a given month/day we don't duplicate the same title
    __table_args__ = (
        UniqueConstraint("month", "day", "title", name="uq_event_month_day_title"),
    )

    # Relationship to clues and game sessions
    clues = relationship("Clue", back_populates="event", cascade="all, delete-orphan")
    game_sessions = relationship(
        "GameSession", back_populates="event", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r} date={self.month}-{self.day}>"


class Clue(Base):
    """
    A clue associated with an event. Clues are shown in order_index sequence to the player.
    """
    __tablename__ = "clues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False)  # 0..N order for reveal
    text = Column(Text, nullable=False)

    event = relationship("Event", back_populates="clues")

    __table_args__ = (
        UniqueConstraint("event_id", "order_index", name="uq_clue_event_order"),
    )

    def __repr__(self) -> str:
        return f"<Clue id={self.id} event_id={self.event_id} order={self.order_index}>"


class GameSession(Base):
    """
    Tracks a single player's game attempt for a specific event.
    """
    __tablename__ = "game_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # gameplay metrics
    attempts_used = Column(Integer, default=0, nullable=False)
    clues_revealed = Column(Integer, default=0, nullable=False)

    # completion flags
    is_completed = Column(Boolean, default=False, nullable=False)
    is_success = Column(Boolean, default=False, nullable=False)

    event = relationship("Event", back_populates="game_sessions")

    def __repr__(self) -> str:
        return f"<GameSession id={self.id} event_id={self.event_id} completed={self.is_completed}>"

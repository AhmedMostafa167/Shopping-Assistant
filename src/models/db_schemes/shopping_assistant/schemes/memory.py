from .base import SQLAlchemyBase
from sqlalchemy import Column, Integer, String, Float, DateTime, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime
import uuid


class Memory(SQLAlchemyBase):

    __tablename__ = "memories"

    memory_id = Column(Integer, primary_key=True, autoincrement=True)
    memory_uuid = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)

    profile_id = Column(Integer, ForeignKey("profiles.profile_id"), nullable=False)
    fact_type = Column(String, nullable=False)  # "preference" | "constraint" | "history"
    content = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    source_turn = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    profile = relationship("Profile", back_populates="memories")

    __table_args__ = (
        Index("ix_memory_profile_id", profile_id),
        Index("ix_memory_fact_type", fact_type),
    )


# ---- Pydantic: agent-facing shapes, not DB rows ----

class ExtractedFact(BaseModel):
    fact_type: Literal["preference", "constraint", "history"]
    content: str
    confidence: float


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact]
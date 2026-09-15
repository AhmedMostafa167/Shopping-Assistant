import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import SQLAlchemyBase


class Conversation(SQLAlchemyBase):
    __tablename__ = "conversations"

    conversation_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Public/application-level identifier.
    conversation_uuid = Column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
    )

    # Internal identifier passed to LangGraph.
    thread_id = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # Existing user/profile owner.
    profile_id = Column(
        Integer,
        ForeignKey("profiles.profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional display name for the conversation.
    title = Column(
        String(255),
        nullable=True,
    )

    # Optional timestamp of the last chat activity.
    last_message_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    profile = relationship(
        "Profile",
        back_populates="conversations",
    )

    __table_args__ = (
        Index(
            "ix_conversations_profile_updated_at",
            "profile_id",
            "updated_at",
        ),
    )

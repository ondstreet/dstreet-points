"""
Community models: bugs, bounties, user stats.
Uses same SQLAlchemy Base as points models (shared).
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from core.models.points import Base
import enum

class BugStatus(enum.Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    FIXED = "fixed"
    REJECTED = "rejected"

class BugReport(Base):
    __tablename__ = "bug_reports"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)  # reporter
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(SQLEnum(BugStatus), default=BugStatus.OPEN, nullable=False)
    severity = Column(String(20), default="normal")  # low, normal, high, critical
    bounty_points = Column(Integer, default=0)       # points offered for fixing
    fixed_by = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=True)  # user who fixed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    # Optional: link to the error report JSON file path
    error_report_path = Column(String(500), nullable=True)

class BountyStatus(enum.Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Bounty(Base):
    __tablename__ = "bounties"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    points_reward = Column(Integer, nullable=False)   # points awarded on completion
    status = Column(SQLEnum(BountyStatus), default=BountyStatus.OPEN, nullable=False)
    claimed_by = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class UserCommunityStats(Base):
    __tablename__ = "user_community_stats"
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), primary_key=True)
    bugs_reported = Column(Integer, default=0)
    bugs_fixed = Column(Integer, default=0)
    bounties_claimed = Column(Integer, default=0)
    bounties_completed = Column(Integer, default=0)
    reputation_score = Column(Integer, default=0)      # sum of points from bounties + bonuses
    level = Column(Integer, default=1)
    badges = Column(Text, default="[]")                # JSON list of badge strings
    last_activity = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NameRegistry(Base):
    """Registered human-readable names mapped to user IDs."""
    __tablename__ = "name_registry"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False, index=True)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    active = Column(Boolean, default=True)
    cost_points = Column(Integer, default=0)  # points paid for registration/renewal
    verified = Column(Boolean, default=False)
    # Relationship (optional)
    owner = relationship("UserPoints", backref="registered_names")

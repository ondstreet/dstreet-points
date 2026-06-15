"""
Points system models for $STORE centralised prototype.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import enum

# Use your existing Base if you have one; otherwise we create a new one.
# If you have a shared base (e.g., in core/database/base.py), import it.
# For now we create a local Base – you can replace with your own.
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

class ProposalStatus(enum.Enum):
    ACTIVE = "active"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"

class VoteChoice(enum.Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"

class UserPoints(Base):
    """User's $STORE point balance and lifetime earnings."""
    __tablename__ = "user_points"
    user_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=True)
    balance = Column(Integer, default=0, nullable=False)
    lifetime_earned = Column(Integer, default=0, nullable=False)
    last_claim = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Stake(Base):
    """Staked points record."""
    __tablename__ = "stakes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    amount = Column(Integer, nullable=False)
    locked_until = Column(DateTime, nullable=False)   # timestamp when stake can be withdrawn
    apy = Column(Float, default=5.0)                  # annual percentage yield (e.g., 5.0 = 5%)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Proposal(Base):
    """Governance proposal."""
    __tablename__ = "proposals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    creator_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    status = Column(SQLEnum(ProposalStatus), default=ProposalStatus.ACTIVE, nullable=False)
    voting_power_yes = Column(Integer, default=0)
    voting_power_no = Column(Integer, default=0)

class Vote(Base):
    """Individual vote on a proposal."""
    __tablename__ = "votes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id = Column(PG_UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    choice = Column(SQLEnum(VoteChoice), nullable=False)
    voting_power = Column(Integer, nullable=False)      # amount of points used for voting (staked + balance)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class RewardLog(Base):
    """Log of point rewards given to users."""
    __tablename__ = "reward_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_points.user_id"), nullable=False)
    amount = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)   # e.g., "commit", "vote", "staking", "daily_mining"
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

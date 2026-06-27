import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String, index=True, nullable=False)  # domain, subdomain, ip_address, service, certificate, technology
    value = Column(String, index=True, nullable=False)
    status = Column(String, default="active", nullable=False)  # active, stale
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    source = Column(String, nullable=False)
    tags = Column(JSONB, default=list, nullable=False)
    
    # We name the python attribute 'metadata_' to avoid conflicts with SQLAlchemy's native 'metadata' property.
    # It maps directly to the database column 'metadata'.
    metadata_ = Column("metadata", JSONB, default=dict, nullable=False)

    # Ensure type and value combination is unique
    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_asset_type_value"),
    )

class AssetRelationship(Base):
    __tablename__ = "asset_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # subdomain_of, runs_on, resolves_to, secures, used_by

    # Relationships to access the Asset objects directly
    source = relationship("Asset", foreign_keys=[source_id], backref="out_relations")
    target = relationship("Asset", foreign_keys=[target_id], backref="in_relations")

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "type", name="uq_relationship_source_target_type"),
    )

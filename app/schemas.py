from datetime import datetime
import ipaddress
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, model_validator, ConfigDict

# ----------------- USER SCHEMAS -----------------

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserOut(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# ----------------- ASSET SCHEMAS -----------------

AssetType = Literal["domain", "subdomain", "ip_address", "service", "certificate", "technology"]
RelationshipType = Literal["subdomain_of", "runs_on", "resolves_to", "secures", "used_by"]

class AssetBase(BaseModel):
    type: AssetType
    value: str = Field(..., min_length=1)
    status: str = Field("active")
    source: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_value_by_type(self) -> 'AssetBase':
        # Custom validation logic depending on asset type
        val = self.value.strip()
        self.value = val

        if self.type == "ip_address":
            try:
                ipaddress.ip_address(val)
            except ValueError:
                raise ValueError(f"'{val}' is not a valid IP address.")
        elif self.type in ["domain", "subdomain"]:
            if " " in val:
                raise ValueError("Domain or subdomain cannot contain spaces.")
            if "." not in val:
                raise ValueError("Domain or subdomain must contain at least one dot (.)")
        elif self.type == "service":
            # e.g., "80/tcp", "443/tcp", or port name
            if not val:
                raise ValueError("Service value cannot be empty.")
        return self

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    type: Optional[AssetType] = None
    value: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_value_by_type(self) -> 'AssetUpdate':
        if self.type is not None and self.value is not None:
            val = self.value.strip()
            if self.type == "ip_address":
                try:
                    ipaddress.ip_address(val)
                except ValueError:
                    raise ValueError(f"'{val}' is not a valid IP address.")
            elif self.type in ["domain", "subdomain"]:
                if " " in val:
                    raise ValueError("Domain or subdomain cannot contain spaces.")
                if "." not in val:
                    raise ValueError("Domain or subdomain must contain at least one dot (.)")
        return self

class AssetOut(BaseModel):
    id: UUID
    type: AssetType
    value: str
    status: str
    first_seen: datetime
    last_seen: datetime
    source: str
    tags: List[str]
    metadata: Dict[str, Any] = Field(..., validation_alias="metadata_", serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# ----------------- RELATIONSHIP SCHEMAS -----------------

class RelationshipCreate(BaseModel):
    source_id: UUID
    target_id: UUID
    type: RelationshipType

class RelationshipOut(BaseModel):
    id: UUID
    source_id: UUID
    target_id: UUID
    type: str

    model_config = ConfigDict(from_attributes=True)

class RelationshipDetailOut(BaseModel):
    id: UUID
    source_id: UUID
    target_id: UUID
    type: str
    source_type: str
    source_value: str
    target_type: str
    target_value: str

    model_config = ConfigDict(from_attributes=True)

# ----------------- BULK IMPORT SCHEMAS -----------------

class BulkImportRequest(BaseModel):
    assets: List[AssetBase]

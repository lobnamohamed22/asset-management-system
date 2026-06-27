from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import Asset, AssetRelationship, User
from app.schemas import AssetCreate, AssetUpdate, RelationshipCreate

# ----------------- USER CRUD -----------------

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user_data: dict) -> User:
    db_user = User(**user_data)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# ----------------- ASSET CRUD -----------------

def get_asset(db: Session, asset_id: UUID) -> Optional[Asset]:
    return db.query(Asset).filter(Asset.id == asset_id).first()

def get_asset_by_type_value(db: Session, asset_type: str, value: str) -> Optional[Asset]:
    return db.query(Asset).filter(Asset.type == asset_type, Asset.value == value).first()

def get_assets(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    sort_by: str = "first_seen",
    sort_order: str = "asc"
) -> List[Asset]:
    query = db.query(Asset)

    # Filtering
    if asset_type:
        query = query.filter(Asset.type == asset_type)
    if status:
        query = query.filter(Asset.status == status)
    if source:
        query = query.filter(Asset.source == source)
    if tag:
        # PostgreSQL JSONB tag list contains the string tag
        query = query.filter(Asset.tags.contains([tag]))

    # Search (case-insensitive in value or metadata JSONB string)
    if search:
        from sqlalchemy import cast, String
        query = query.filter(
            Asset.value.ilike(f"%{search}%") | 
            cast(Asset.metadata_, String).ilike(f"%{search}%")
        )

    # Sorting
    if hasattr(Asset, sort_by):
        sort_attr = getattr(Asset, sort_by)
        if sort_order.lower() == "desc":
            sort_attr = sort_attr.desc()
        query = query.order_by(sort_attr)
    else:
        query = query.order_by(Asset.first_seen.asc())

    return query.offset(skip).limit(limit).all()

def create_asset(db: Session, asset_in: AssetCreate) -> Asset:
    db_asset = Asset(
        type=asset_in.type,
        value=asset_in.value,
        status=asset_in.status,
        source=asset_in.source,
        tags=asset_in.tags,
        metadata_=asset_in.metadata
    )
    db.add(db_asset)
    db.commit()
    db.refresh(db_asset)
    return db_asset

def update_asset(db: Session, asset_id: UUID, asset_in: AssetUpdate) -> Optional[Asset]:
    db_asset = get_asset(db, asset_id)
    if not db_asset:
        return None

    update_data = asset_in.model_dump(exclude_unset=True)
    
    # Map 'metadata' in schema to 'metadata_' in DB model
    if "metadata" in update_data:
        db_asset.metadata_ = update_data.pop("metadata")

    for key, value in update_data.items():
        setattr(db_asset, key, value)

    # Always update last_seen on modification
    db_asset.last_seen = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_asset)
    return db_asset

def delete_asset(db: Session, asset_id: UUID) -> bool:
    db_asset = get_asset(db, asset_id)
    if not db_asset:
        return False
    db.delete(db_asset)
    db.commit()
    return True

# ----------------- TAG MANAGEMENT -----------------

def add_tag_to_asset(db: Session, asset_id: UUID, tag: str) -> Optional[Asset]:
    db_asset = get_asset(db, asset_id)
    if not db_asset:
        return None
    
    # Ensure tags is a list and avoid duplicates
    tags_list = list(db_asset.tags) if db_asset.tags else []
    if tag not in tags_list:
        tags_list.append(tag)
        db_asset.tags = tags_list
        db_asset.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_asset)
    return db_asset

def remove_tag_from_asset(db: Session, asset_id: UUID, tag: str) -> Optional[Asset]:
    db_asset = get_asset(db, asset_id)
    if not db_asset:
        return None
    
    tags_list = list(db_asset.tags) if db_asset.tags else []
    if tag in tags_list:
        tags_list.remove(tag)
        db_asset.tags = tags_list
        db_asset.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_asset)
    return db_asset

def get_all_tags(db: Session) -> List[str]:
    # Raw query to fetch unique elements from JSONB array
    result = db.execute(text("SELECT DISTINCT jsonb_array_elements_text(tags) FROM assets"))
    return [row[0] for row in result.all()]

# ----------------- RELATIONSHIPS -----------------

def create_relationship(db: Session, rel_in: RelationshipCreate) -> AssetRelationship:
    # Check if the relationship already exists to avoid unique constraint error
    existing = db.query(AssetRelationship).filter_by(
        source_id=rel_in.source_id,
        target_id=rel_in.target_id,
        type=rel_in.type
    ).first()
    if existing:
        return existing

    db_rel = AssetRelationship(
        source_id=rel_in.source_id,
        target_id=rel_in.target_id,
        type=rel_in.type
    )
    db.add(db_rel)
    db.commit()
    db.refresh(db_rel)
    return db_rel

def get_relationships_for_asset(db: Session, asset_id: UUID) -> List[AssetRelationship]:
    # Returns all relationships where the asset is either the source or target
    return db.query(AssetRelationship).filter(
        (AssetRelationship.source_id == asset_id) | (AssetRelationship.target_id == asset_id)
    ).all()

def delete_relationship(db: Session, rel_id: UUID) -> bool:
    db_rel = db.query(AssetRelationship).filter(AssetRelationship.id == rel_id).first()
    if not db_rel:
        return False
    db.delete(db_rel)
    db.commit()
    return True

# ----------------- BULK IMPORT & DEDUPLICATION -----------------

def bulk_import_assets(db: Session, assets_in: List[AssetCreate]) -> List[Asset]:
    imported_assets = []
    now = datetime.now(timezone.utc)

    for asset_schema in assets_in:
        # Check if asset with same type and value exists
        existing_asset = get_asset_by_type_value(db, asset_schema.type, asset_schema.value)

        if existing_asset:
            # 1. Deduplication: Merge metadata
            merged_metadata = dict(existing_asset.metadata_)
            merged_metadata.update(asset_schema.metadata)
            existing_asset.metadata_ = merged_metadata

            # 2. Deduplication: Merge tags (union of sets)
            merged_tags = list(set(existing_asset.tags) | set(asset_schema.tags))
            existing_asset.tags = merged_tags

            # 3. Lifecycle: Update last_seen
            existing_asset.last_seen = now

            # 4. Lifecycle: Restore active on re-import if status was stale
            if existing_asset.status == "stale":
                existing_asset.status = "active"

            imported_assets.append(existing_asset)
        else:
            # New asset: Create with current times
            new_asset = Asset(
                type=asset_schema.type,
                value=asset_schema.value,
                status="active",
                first_seen=now,
                last_seen=now,
                source=asset_schema.source,
                tags=asset_schema.tags,
                metadata_=asset_schema.metadata
            )
            db.add(new_asset)
            imported_assets.append(new_asset)

    db.commit()
    # Refresh imported assets to get their database IDs
    for asset in imported_assets:
        db.refresh(asset)

    # Run automated relation inference
    infer_relationships(db, imported_assets)

    return imported_assets

# ----------------- LIFECYCLE MANAGEMENT -----------------

def mark_stale_assets(db: Session, days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # Query active assets not seen since cutoff
    stale_assets = db.query(Asset).filter(
        Asset.status == "active",
        Asset.last_seen < cutoff
    ).all()

    for asset in stale_assets:
        asset.status = "stale"

    db.commit()
    return len(stale_assets)

# ----------------- RELATION INFERENCE ENGINE -----------------

def infer_relationships(db: Session, assets: List[Asset]):
    """
    Automated relationship inference engine based on assignment rules.
    Runs on imported/updated assets and evaluates rules bidirectionally.
    """
    all_assets = db.query(Asset).all()
    
    domains = [a for a in all_assets if a.type == "domain"]
    subdomains = [a for a in all_assets if a.type == "subdomain"]
    ips = {a.value: a for a in all_assets if a.type == "ip_address"}
    services = [a for a in all_assets if a.type == "service"]
    certs = [a for a in all_assets if a.type == "certificate"]
    techs = [a for a in all_assets if a.type == "technology"]

    for asset in assets:
        # Rule 1: subdomain -> domain (subdomain_of)
        if asset.type == "subdomain":
            for domain in domains:
                if asset.value.endswith("." + domain.value) or asset.value == domain.value:
                    create_relationship(db, RelationshipCreate(
                        source_id=asset.id,
                        target_id=domain.id,
                        type="subdomain_of"
                    ))
        elif asset.type == "domain":
            for sub in subdomains:
                if sub.value.endswith("." + asset.value) or sub.value == asset.value:
                    create_relationship(db, RelationshipCreate(
                        source_id=sub.id,
                        target_id=asset.id,
                        type="subdomain_of"
                    ))

        # Rule 2: service -> ip_address (runs_on)
        if asset.type == "service":
            ip_val = asset.metadata_.get("ip_address") or asset.metadata_.get("ip")
            if ip_val and ip_val in ips:
                create_relationship(db, RelationshipCreate(
                    source_id=asset.id,
                    target_id=ips[ip_val].id,
                    type="runs_on"
                ))
        elif asset.type == "ip_address":
            for svc in services:
                ip_val = svc.metadata_.get("ip_address") or svc.metadata_.get("ip")
                if ip_val == asset.value:
                    create_relationship(db, RelationshipCreate(
                        source_id=svc.id,
                        target_id=asset.id,
                        type="runs_on"
                    ))

        # Rule 3: ip_address <-> subdomain (resolves_to)
        if asset.type == "subdomain":
            res_ips = asset.metadata_.get("ip_address") or asset.metadata_.get("ips") or asset.metadata_.get("resolves_to", [])
            if isinstance(res_ips, str) and res_ips in ips:
                create_relationship(db, RelationshipCreate(
                    source_id=asset.id,
                    target_id=ips[res_ips].id,
                    type="resolves_to"
                ))
            elif isinstance(res_ips, list):
                for rip in res_ips:
                    if rip in ips:
                        create_relationship(db, RelationshipCreate(
                            source_id=asset.id,
                            target_id=ips[rip].id,
                            type="resolves_to"
                        ))
        elif asset.type == "ip_address":
            for sub in subdomains:
                res_ips = sub.metadata_.get("ip_address") or sub.metadata_.get("ips") or sub.metadata_.get("resolves_to", [])
                if isinstance(res_ips, str) and res_ips == asset.value:
                    create_relationship(db, RelationshipCreate(
                        source_id=sub.id,
                        target_id=asset.id,
                        type="resolves_to"
                    ))
                elif isinstance(res_ips, list) and asset.value in res_ips:
                    create_relationship(db, RelationshipCreate(
                        source_id=sub.id,
                        target_id=asset.id,
                        type="resolves_to"
                    ))

        # Rule 4: certificate -> domain/subdomain (secures)
        if asset.type == "certificate":
            cert_domains = asset.metadata_.get("domains") or asset.metadata_.get("domain") or asset.metadata_.get("subject_alternative_names", [])
            if isinstance(cert_domains, str):
                cert_domains = [cert_domains]
            for c_dom in cert_domains:
                target_asset = next((a for a in all_assets if a.type in ["domain", "subdomain"] and a.value == c_dom), None)
                if target_asset:
                    create_relationship(db, RelationshipCreate(
                        source_id=asset.id,
                        target_id=target_asset.id,
                        type="secures"
                    ))
        elif asset.type in ["domain", "subdomain"]:
            for cert in certs:
                cert_domains = cert.metadata_.get("domains") or cert.metadata_.get("domain") or cert.metadata_.get("subject_alternative_names", [])
                if isinstance(cert_domains, str):
                    cert_domains = [cert_domains]
                if asset.value in cert_domains:
                    create_relationship(db, RelationshipCreate(
                        source_id=cert.id,
                        target_id=asset.id,
                        type="secures"
                    ))

        # Rule 5: technology -> service/subdomain (used_by)
        if asset.type == "technology":
            tech_services = asset.metadata_.get("services") or asset.metadata_.get("service") or []
            tech_subs = asset.metadata_.get("subdomains") or asset.metadata_.get("subdomain") or []
            if isinstance(tech_services, str): tech_services = [tech_services]
            if isinstance(tech_subs, str): tech_subs = [tech_subs]

            for s_val in tech_services:
                target_svc = next((a for a in services if a.value == s_val), None)
                if target_svc:
                    create_relationship(db, RelationshipCreate(
                        source_id=asset.id,
                        target_id=target_svc.id,
                        type="used_by"
                    ))
            for sub_val in tech_subs:
                target_sub = next((a for a in subdomains if a.value == sub_val), None)
                if target_sub:
                    create_relationship(db, RelationshipCreate(
                        source_id=asset.id,
                        target_id=target_sub.id,
                        type="used_by"
                    ))
        elif asset.type == "service":
            for tech in techs:
                tech_services = tech.metadata_.get("services") or tech.metadata_.get("service") or []
                if isinstance(tech_services, str): tech_services = [tech_services]
                if asset.value in tech_services:
                    create_relationship(db, RelationshipCreate(
                        source_id=tech.id,
                        target_id=asset.id,
                        type="used_by"
                    ))
        elif asset.type == "subdomain":
            for tech in techs:
                tech_subs = tech.metadata_.get("subdomains") or tech.metadata_.get("subdomain") or []
                if isinstance(tech_subs, str): tech_subs = [tech_subs]
                if asset.value in tech_subs:
                    create_relationship(db, RelationshipCreate(
                        source_id=tech.id,
                        target_id=asset.id,
                        type="used_by"
                    ))

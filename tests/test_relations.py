import pytest
from fastapi import status

@pytest.fixture
def auth_headers(client):
    """Fixture to return auth headers for a registered test user."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "relationuser", "email": "relation@example.com", "password": "password123"}
    )
    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": "relationuser", "password": "password123"}
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_explicit_relationship_crud(client, auth_headers):
    # Create two assets
    asset1_res = client.post("/api/v1/assets", json={"type": "domain", "value": "domain.com", "source": "manual"}, headers=auth_headers)
    asset2_res = client.post("/api/v1/assets", json={"type": "subdomain", "value": "sub.domain.com", "source": "manual"}, headers=auth_headers)
    
    id1 = asset1_res.json()["id"]
    id2 = asset2_res.json()["id"]

    # Create relationship
    rel_res = client.post(
        "/api/v1/relationships",
        json={"source_id": id2, "target_id": id1, "type": "subdomain_of"},
        headers=auth_headers
    )
    assert rel_res.status_code == status.HTTP_201_CREATED
    rel_data = rel_res.json()
    assert rel_data["source_id"] == id2
    assert rel_data["target_id"] == id1
    assert rel_data["type"] == "subdomain_of"
    rel_id = rel_data["id"]

    # Get asset relationships
    get_res = client.get(f"/api/v1/assets/{id2}/relationships", headers=auth_headers)
    assert get_res.status_code == status.HTTP_200_OK
    assert len(get_res.json()) == 1
    assert get_res.json()[0]["id"] == rel_id

    # Delete relationship
    del_res = client.delete(f"/api/v1/relationships/{rel_id}", headers=auth_headers)
    assert del_res.status_code == status.HTTP_204_NO_CONTENT

    # Check it's gone
    get_res_after = client.get(f"/api/v1/assets/{id2}/relationships", headers=auth_headers)
    assert len(get_res_after.json()) == 0

def test_automatic_relationship_inference(client, auth_headers):
    # Import assets that trigger relationships
    payload = {
        "assets": [
            {
                "type": "domain",
                "value": "inferred.com",
                "source": "recon"
            },
            {
                "type": "subdomain",
                "value": "dev.inferred.com",
                "source": "recon",
                "metadata": {"ip_address": "1.2.3.4"}
            },
            {
                "type": "ip_address",
                "value": "1.2.3.4",
                "source": "recon"
            },
            {
                "type": "service",
                "value": "80/tcp",
                "source": "recon",
                "metadata": {"ip_address": "1.2.3.4"}
            },
            {
                "type": "certificate",
                "value": "inferred-cert",
                "source": "recon",
                "metadata": {"domains": ["inferred.com"]}
            },
            {
                "type": "technology",
                "value": "Nginx",
                "source": "recon",
                "metadata": {"services": ["80/tcp"]}
            }
        ]
    }
    
    # Bulk import
    import_res = client.post("/api/v1/assets/import", json=payload, headers=auth_headers)
    assert import_res.status_code == status.HTTP_200_OK
    
    assets_map = {a["value"]: a["id"] for a in import_res.json()}

    # 1. Check subdomain -> domain (subdomain_of)
    sub_id = assets_map["dev.inferred.com"]
    dom_id = assets_map["inferred.com"]
    res1 = client.get(f"/api/v1/assets/{sub_id}/relationships", headers=auth_headers)
    relations1 = res1.json()
    assert any(r["source_id"] == sub_id and r["target_id"] == dom_id and r["type"] == "subdomain_of" for r in relations1)

    # 2. Check service -> ip_address (runs_on)
    svc_id = assets_map["80/tcp"]
    ip_id = assets_map["1.2.3.4"]
    res2 = client.get(f"/api/v1/assets/{svc_id}/relationships", headers=auth_headers)
    relations2 = res2.json()
    assert any(r["source_id"] == svc_id and r["target_id"] == ip_id and r["type"] == "runs_on" for r in relations2)

    # 3. Check ip_address <-> subdomain (resolves_to)
    # The subdomain resolves to the ip_address
    assert any(r["source_id"] == sub_id and r["target_id"] == ip_id and r["type"] == "resolves_to" for r in relations1)

    # 4. Check certificate -> domain (secures)
    cert_id = assets_map["inferred-cert"]
    res4 = client.get(f"/api/v1/assets/{cert_id}/relationships", headers=auth_headers)
    relations4 = res4.json()
    assert any(r["source_id"] == cert_id and r["target_id"] == dom_id and r["type"] == "secures" for r in relations4)

    # 5. Check technology -> service (used_by)
    tech_id = assets_map["Nginx"]
    res5 = client.get(f"/api/v1/assets/{tech_id}/relationships", headers=auth_headers)
    relations5 = res5.json()
    assert any(r["source_id"] == tech_id and r["target_id"] == svc_id and r["type"] == "used_by" for r in relations5)

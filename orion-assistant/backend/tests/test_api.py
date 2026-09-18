def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_root(client):
    assert client.get("/").json()["name"] == "ORION"


def test_status(client):
    body = client.get("/v1/system/status").json()
    assert "providers" in body and "counts" in body


def test_tools_listing(client):
    tools = client.get("/v1/tools").json()["tools"]
    assert any(t["name"] == "calculate" for t in tools)


def test_run_tool(client):
    r = client.post("/v1/tools/run", json={"name": "calculate", "arguments": {"expression": "6*7"}})
    assert r.json()["result"]["result"] == 42


def test_tool_requiring_approval_creates_request(client):
    r = client.post("/v1/tools/run", json={"name": "write_file", "arguments": {"path": "a.txt", "content": "x"}})
    body = r.json()
    assert body["approval_required"] is True
    approvals = client.get("/v1/approvals").json()["approvals"]
    assert any(a["id"] == body["approval_id"] for a in approvals)

    done = client.post(f"/v1/approvals/{body['approval_id']}", json={"approve": True, "execute": True}).json()
    assert done["status"] == "approved" and done["result"]["ok"] is True


def test_memory_endpoints(client):
    created = client.post("/v1/memory", json={"content": "Orion ships with SQLite by default.", "kind": "fact"})
    assert created.status_code == 200
    found = client.get("/v1/memory/search", params={"q": "default database"}).json()["results"]
    assert found


def test_knowledge_ingest_and_search(client):
    client.post("/v1/knowledge/ingest-text", json={"name": "spec.md", "content": "The agent loop supports six tool iterations."})
    results = client.get("/v1/knowledge/search", params={"q": "tool iterations"}).json()["results"]
    assert results
    assert client.get("/v1/knowledge/documents").json()["documents"]


def test_chat_degrades_gracefully(client):
    body = client.post("/v1/chat", json={"message": "hello orion"}).json()
    assert body["conversation_id"]
    assert body["result"]
    convo = client.get(f"/v1/conversations/{body['conversation_id']}").json()
    assert len(convo["messages"]) >= 2


def test_settings_patch(client):
    body = client.patch("/v1/settings", json={"max_tool_loops": 5}).json()
    assert body["max_tool_loops"] == 5


def test_kill_switch(client):
    assert client.post("/v1/security/kill-switch", json={"enabled": True, "reason": "test"}).json()["enabled"]
    assert client.post("/v1/security/kill-switch", json={"enabled": False}).json()["enabled"] is False


def test_automation_crud(client):
    created = client.post("/v1/automations", json={"name": "daily", "prompt": "summarize", "schedule_seconds": 3600})
    aid = created.json()["id"]
    assert any(a["id"] == aid for a in client.get("/v1/automations").json()["automations"])
    assert client.delete(f"/v1/automations/{aid}").json()["deleted"]


def test_metrics_and_audit(client):
    assert "router" in client.get("/v1/system/metrics").json()
    assert "events" in client.get("/v1/audit").json()

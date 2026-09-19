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


def test_conversation_rename(client):
    cid = client.post("/v1/chat", json={"message": "rename me"}).json()["conversation_id"]
    body = client.patch(f"/v1/conversations/{cid}", json={"title": "Renamed thread"}).json()
    assert body["title"] == "Renamed thread"
    listed = client.get("/v1/conversations").json()["conversations"]
    assert any(c["id"] == cid and c["title"] == "Renamed thread" for c in listed)


def test_conversation_pin_sorts_first(client):
    first = client.post("/v1/chat", json={"message": "older"}).json()["conversation_id"]
    client.post("/v1/chat", json={"message": "newer"})
    client.patch(f"/v1/conversations/{first}", json={"pinned": True})
    listed = client.get("/v1/conversations").json()["conversations"]
    assert listed[0]["id"] == first, "pinned conversations must sort to the top"


def test_conversation_archive_hides_by_default(client):
    cid = client.post("/v1/chat", json={"message": "archive me"}).json()["conversation_id"]
    client.patch(f"/v1/conversations/{cid}", json={"archived": True})

    visible = client.get("/v1/conversations").json()["conversations"]
    assert all(c["id"] != cid for c in visible)

    with_archived = client.get("/v1/conversations", params={"include_archived": True}).json()["conversations"]
    assert any(c["id"] == cid for c in with_archived)


def test_conversation_patch_validation(client):
    cid = client.post("/v1/chat", json={"message": "validate"}).json()["conversation_id"]
    assert client.patch(f"/v1/conversations/{cid}", json={}).status_code == 400
    assert client.patch("/v1/conversations/does-not-exist", json={"title": "x"}).status_code == 404


# ------------------------------------------------- conversation resolution
def test_an_unknown_conversation_id_is_a_404_not_a_new_conversation(client):
    """The buffered path used to adopt whatever id it was handed and create a
    row with it. That let a caller choose primary keys, and a stale tab would
    silently fork history into a conversation the user never opened."""
    response = client.post(
        "/v1/chat", json={"message": "hello", "conversation_id": "ghost-12345"}
    )
    assert response.status_code == 404
    assert "ghost-12345" in response.json()["detail"]


def test_the_streaming_endpoint_agrees(client):
    """Both paths had different behaviour for the same request."""
    response = client.post(
        "/v1/chat/stream", json={"message": "hello", "conversation_id": "ghost-12345"}
    )
    assert response.status_code == 404


def test_a_rejected_id_creates_nothing(client):
    before = len(client.get("/v1/conversations?limit=500").json()["conversations"])
    client.post("/v1/chat", json={"message": "hello", "conversation_id": "ghost-abc"})
    after = len(client.get("/v1/conversations?limit=500").json()["conversations"])
    assert after == before


def test_omitting_the_id_still_starts_a_conversation(client):
    body = client.post("/v1/chat", json={"message": "start fresh"}).json()
    assert body["conversation_id"]


def test_an_existing_conversation_continues(client):
    first = client.post("/v1/chat", json={"message": "one"}).json()
    second = client.post(
        "/v1/chat", json={"message": "two", "conversation_id": first["conversation_id"]}
    ).json()

    assert second["conversation_id"] == first["conversation_id"]
    messages = client.get(f"/v1/conversations/{first['conversation_id']}").json()["messages"]
    assert [m["content"] for m in messages if m["role"] == "user"] == ["one", "two"]

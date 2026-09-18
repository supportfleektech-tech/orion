from app.tools.registry import ToolRegistry, ToolDefinition


def test_registry_schema():
    reg = ToolRegistry()
    reg.register(ToolDefinition("x", "x tool", {"type":"object"}))
    schemas = reg.openai_schemas()
    assert schemas[0]["function"]["name"] == "x"

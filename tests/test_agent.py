def test_agent_registry_is_read_only(players, fixtures, team, rules):
    from fpl_agent.agent import build_tool_registry

    registry = build_tool_registry(players, fixtures, team, rules)
    names = {schema["function"]["name"] for schema in registry.schemas}
    assert names == {
        "get_rules_summary",
        "validate_current_team",
        "get_player_evidence",
        "find_player_by_name",
        "calculate_recommendation",
    }
    assert not any("execute" in name or "transfer" == name for name in names)


def test_agent_tool_returns_structured_recommendation(players, fixtures, team, rules):
    from fpl_agent.agent import build_tool_registry

    registry = build_tool_registry(players, fixtures, team, rules)
    result = registry.call(
        "calculate_recommendation", {"gameweek": 4, "horizon": 3, "max_transfers": 1}
    )
    assert result["gameweek"] == 4
    assert len(result["plans"]) == 2
    assert result["player_directory"]["6"]["name"] == "Flint"


def test_agent_can_resolve_a_name(players, fixtures, team, rules):
    from fpl_agent.agent import build_tool_registry

    result = build_tool_registry(players, fixtures, team, rules).call(
        "find_player_by_name", {"name": "flint"}
    )
    assert result["matches"][0]["player_id"] == 6


def test_registry_records_tool_results(players, fixtures, team, rules):
    from fpl_agent.agent import build_tool_registry

    registry = build_tool_registry(players, fixtures, team, rules)
    registry.call("validate_current_team", {})
    assert registry.last_result("validate_current_team")["valid"] is True
    assert registry.last_result("calculate_recommendation") is None

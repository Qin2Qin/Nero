from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CURRENT_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "demo-script.md",
    ROOT / "docs" / "xero-app-store-submission.md",
    ROOT / "docs" / "xero-hackathon-and-mcp.md",
]
ARCHIVED_BUILD_GUIDE = ROOT / "nero-build-guide-with-prompts.md"


def test_current_docs_do_not_claim_unverified_mcp_execution() -> None:
    combined = "\n".join(path.read_text() for path in CURRENT_DOCS)

    assert "MCP-native" not in combined
    assert "via MCP" not in combined
    assert "do not fake MCP usage" in combined
    assert "does not currently expose callable Xero MCP tools" in combined


def test_current_docs_describe_agent_boundary_without_overclaiming_llm_runtime() -> None:
    combined = "\n".join(path.read_text() for path in CURRENT_DOCS)

    assert "deterministic local agent logic" in combined
    assert "approval-gated" in combined
    assert "No customer-facing action is sent automatically" in combined
    assert "Do not use app-runtime inference credentials for development automation" in combined
    assert "do not pitch LLM-written emails" in combined
    assert "LLM-written emails are implemented" not in combined
    assert "supports autonomous sending" not in combined


def test_archived_build_guide_is_marked_non_authoritative() -> None:
    text = ARCHIVED_BUILD_GUIDE.read_text()

    assert "Archived planning note, not current implementation evidence" in text
    assert "must not be used in the final pitch" in text

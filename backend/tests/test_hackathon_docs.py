from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CURRENT_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "demo-script.md",
    ROOT / "docs" / "final-submission-answers.md",
    ROOT / "docs" / "xero-app-store-submission.md",
    ROOT / "docs" / "xero-hackathon-and-mcp.md",
]
ARCHIVED_BUILD_GUIDE = ROOT / "nero-build-guide-with-prompts.md"
PROJECT_IMAGE = ROOT / "frontend" / "public" / "visuals" / "nero-cashflow-preview.png"


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
    assert "optional app-runtime free inference can polish draft wording only" in combined
    assert "OPENROUTER_MODEL` ends in `:free" in combined
    assert "still requires manual approval" in combined
    assert "LLM-written emails are implemented" not in combined
    assert "supports autonomous sending" not in combined


def test_current_docs_preserve_hackathon_requirements_and_judging_weights() -> None:
    text = (ROOT / "docs" / "xero-hackathon-and-mcp.md").read_text()

    for requirement in (
        "Use Xero's APIs.",
        "Use the Xero MCP Server.",
        "Use CLI tooling.",
        "Use an AI toolkit.",
    ):
        assert requirement in text

    assert "50% Xero Connection" in text
    assert "30% API Integration" in text
    assert "20% Architecture" in text
    assert "Utilize AI for complex scenarios" in text


def test_final_submission_answers_match_current_xero_integration() -> None:
    text = (ROOT / "docs" / "final-submission-answers.md").read_text()

    assert "Nero (FlowCast)" in text
    assert "frontend/public/visuals/nero-cashflow-preview.png" in text
    assert PROJECT_IMAGE.exists()
    for endpoint in (
        "GET /Contacts",
        "GET /Invoices?Statuses=AUTHORISED,PAID",
        "GET /Invoices/{InvoiceID}/OnlineInvoice",
        "GET /Payments",
        "PUT /Invoices/{InvoiceID}/History",
    ):
        assert endpoint in text
    assert "openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access" in text
    assert "do not claim fake MCP execution" in text
    assert "Development automation stayed in the Codex harness" in text


def test_archived_build_guide_is_marked_non_authoritative() -> None:
    text = ARCHIVED_BUILD_GUIDE.read_text()

    assert "Archived planning note, not current implementation evidence" in text
    assert "must not be used in the final pitch" in text

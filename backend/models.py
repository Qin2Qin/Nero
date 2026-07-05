from __future__ import annotations

from typing import Literal, Optional

try:
    from pydantic import BaseModel
except ModuleNotFoundError:  # Keeps pure service tests usable before backend deps are installed.
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)


Grade = Literal["A", "B", "C", "D", "E", "C (low data)"]
ProposalType = Literal["reminder", "escalation", "deposit_recommendation", "terms_recommendation"]
ProposalStatus = Literal["pending", "approved", "dismissed"]


class Contact(BaseModel):
    id: str
    name: str
    revenue_12m: int
    grade: Grade
    avg_days_late: float
    stdev_days_late: float
    trend_slope: float
    invoice_count: int
    explanation: Optional[str] = None
    low_confidence: bool = False


class Invoice(BaseModel):
    id: str
    contact_id: str
    contact_name: str
    invoice_number: str
    amount_due: int
    issue_date: str
    due_date: str
    status: str
    predicted_paid_date: str
    accelerated_paid_date: Optional[str] = None
    online_invoice_url: Optional[str] = None


class Proposal(BaseModel):
    id: str
    type: ProposalType
    contact_id: str
    contact_name: str
    contact_email: Optional[str] = None
    invoice_id: Optional[str]
    reasoning_text: str
    draft_subject: Optional[str]
    draft_body: Optional[str]
    recommendation_detail: Optional[str]
    expected_impact_dollars: int
    expected_days_accelerated: int
    status: ProposalStatus


class ActionLogEntry(BaseModel):
    id: str
    timestamp: str
    actor: str
    event: str


class OutboxEntry(BaseModel):
    id: str
    timestamp: str
    to: str
    to_email: Optional[str] = None
    subject: str
    body: str
    invoice_id: Optional[str] = None
    proposal_id: Optional[str] = None

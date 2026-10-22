"""Example: bid-generation pipeline.

A bid-generation pipeline (parse → compose → audit). Shows how to use
``agent-harness`` for a longer linear lifecycle with two paths (auto-generate
vs upload-existing).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from agent_harness import (
    StateMachine,
    checkpoint,
    derive_state_from_flags,
    set_default_fields,
)


class BidState(Enum):
    INIT = "init"
    PARSING = "parsing"
    PARSED = "parsed"        # spec ready
    COMPOSING = "composing"
    COMPOSED = "composed"    # bid docx ready
    AUDITING = "auditing"
    AUDITED = "audited"      # terminal success
    FAILED = "failed"        # any error path


def _parsed_inv(t):
    assert t.get("tender_spec"), "PARSED requires tender_spec"


def _composed_inv(t):
    assert t.get("bid_docx"), "COMPOSED requires bid_docx"


def _audited_inv(t):
    assert t.get("audit_json"), "AUDITED requires audit_json"


def _failed_inv(t):
    cause = t.get("failure_cause")
    reason = t.get("finish_reason") or ""
    assert cause or reason.startswith("failed") or reason == "interrupted"


sm = StateMachine(
    state_enum=BidState,
    transitions={
        (BidState.INIT, "parse_start"):    BidState.PARSING,
        (BidState.PARSING, "parse_done"):  BidState.PARSED,
        (BidState.PARSING, "parse_failed"): BidState.FAILED,
        (BidState.PARSED, "parse_start"):  BidState.PARSING,   # re-parse
        # Path A: auto-generate
        (BidState.PARSED, "compose_start"):  BidState.COMPOSING,
        (BidState.COMPOSING, "compose_done"): BidState.COMPOSED,
        (BidState.COMPOSING, "compose_failed"): BidState.FAILED,
        # Path B: upload existing
        (BidState.PARSED, "upload_bid"):    BidState.COMPOSED,
        (BidState.COMPOSED, "upload_bid"):  BidState.COMPOSED,  # replace
        # Audit
        (BidState.COMPOSED, "audit_start"):   BidState.AUDITING,
        (BidState.AUDITING, "audit_done"):    BidState.AUDITED,
        (BidState.AUDITING, "audit_failed"):  BidState.FAILED,
        # Re-audit
        (BidState.AUDITED, "audit_start"):    BidState.AUDITING,
        (BidState.AUDITED, "parse_start"):    BidState.PARSING,
        # Abort
        **{(s, "abort"): BidState.FAILED for s in (
            BidState.INIT, BidState.PARSING, BidState.PARSED,
            BidState.COMPOSING, BidState.COMPOSED, BidState.AUDITING,
        )},
    },
    invariants={
        BidState.PARSED:   _parsed_inv,
        BidState.COMPOSED: _composed_inv,
        BidState.AUDITED:  _audited_inv,
        BidState.FAILED:   _failed_inv,
    },
)


# Tasks loaded from data/tasks.json that pre-date the state machine: derive.
def migrate_legacy_task(t: dict) -> None:
    if "state" not in t:
        rules = [
            (lambda x: bool(x.get("audit_json")), BidState.AUDITED),
            (lambda x: bool(x.get("bid_docx")),   BidState.COMPOSED),
            (lambda x: bool(x.get("tender_spec")), BidState.PARSED),
        ]
        t["state"] = derive_state_from_flags(t, rules, default=BidState.INIT).value


set_default_fields([
    "id", "name", "company",
    "state", "current_step",
    "tender_pdf", "tender_spec", "bid_docx",
    "audit_json", "audit_summary",
    "finished", "failure_cause",
])


def main():
    wf = Path("data/bids/T-007")
    wf.mkdir(parents=True, exist_ok=True)
    task = {"id": "T-007", "name": "demo", "company": "测试公司",
            "state": BidState.INIT.value}

    # Parse
    sm.transition(task, "parse_start")
    task["tender_pdf"] = "/data/tenders/x.pdf"
    task["tender_spec"] = "/data/output/x.tender.json"
    sm.transition(task, "parse_done")
    checkpoint(task, wf, "parse_done", detail="13 score items")

    # Path B: upload existing
    task["bid_docx"] = "/data/bids/T-007/bid.docx"
    sm.transition(task, "upload_bid")
    checkpoint(task, wf, "upload_bid")

    # Audit
    sm.transition(task, "audit_start")
    task["audit_json"] = "/data/bids/T-007/audit.json"
    task["audit_summary"] = {"fatal": 0, "score": 78}
    sm.transition(task, "audit_done")
    checkpoint(task, wf, "audit_done", detail="score=78 fatal=0")

    print(f"Final state: {task['state']}")


if __name__ == "__main__":
    main()

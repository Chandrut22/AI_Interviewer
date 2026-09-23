import os
import json 
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Literal
from agent.state import Mode

load_dotenv()

SENIORITY_BASELINE = json.loads(os.getenv("SENIORITY_BASELINE", "{}"))

Action = Literal["continue_topic", "next_topic", "wrap_up"]

def baseline_difficulty(seniority: str | None, years_required: float = 0.0) -> int:
    """Starting difficulty for a topic, from the JD's seniority signal."""
    if seniority:
        level = SENIORITY_BASELINE.get(seniority.strip().lower())
        if level:
            return level
    if years_required >= 8:
        return 5
    if years_required >= 5:
        return 4
    if years_required >= 2:
        return 3
    return 2


def topic_difficulty(baseline: int, is_claimed_on_resume: bool, is_gap: bool = False) -> int:
    level = baseline + (1 if is_claimed_on_resume else 0) - (1 if is_gap else 0)
    return max(1, min(5, level))

def wrap_up_reserve(total_seconds: int) -> int:
    """Time held back so the interview can close gracefully."""
    return max(60, int(total_seconds * 0.08))



def depth_credit(answer_score: float, difficulty: int, timed_out: bool) -> int:
    if timed_out or answer_score < 2.5:
        return 0
    if answer_score >= 4.0:
        return 2 if difficulty >= 3 else 1
    return 1




def coverage_ratio(covered: int, planned: int) -> float:
    return round(covered / planned, 2) if planned else 0.0

def borrow_from_last_topics(
    current_topic_id: str,
    seconds: int,
    topics: list,
    order: list[str],
    topic_runs: dict,
    min_seconds: int = 100,
) -> tuple[list, int, dict[str, int]]:
    """Give the current topic up to `seconds` extra, taken from the LAST pending
    topics in plan order, never leaving a donor below `min_seconds`.

    Returns (topics, seconds_granted, {donor_id: seconds_taken}).
    Total interview time is unchanged.
    """
    by_id = {t.id: t for t in topics}
    current = by_id.get(current_topic_id)
    if current is None or seconds <= 0:
        return topics, 0, {}

    donors: dict[str, int] = {}
    needed = seconds
    for tid in reversed(order):
        if needed <= 0:
            break
        if tid == current_topic_id or tid not in by_id:
            continue
        run = topic_runs.get(tid)
        if run is None or run.status != "pending":
            continue
        donor = by_id[tid]
        take = min(needed, max(0, donor.allocated_seconds - min_seconds))
        if take > 0:
            donor.allocated_seconds -= take
            donors[tid] = take
            needed -= take

    granted = seconds - needed
    current.allocated_seconds += granted
    return topics, granted, donors
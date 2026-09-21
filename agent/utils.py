import os
import json 
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Literal
from agent.state import Mode

load_dotenv()

SENIORITY_BASELINE = json.loads(os.getenv("SENIORITY_BASELINE", "{}"))

Action = Literal["continue_topic", "next_topic", "wrap_up"]

@dataclass(frozen=True)
class Pacing:
    action: Action
    reason: str

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

def adjust_difficulty(current: int, answer_score: float, baseline: int) -> int:
    if answer_score >= 4.2:
        nxt = current + 1
    elif answer_score <= 2.2:
        nxt = current - 1
    else:
        nxt = current
    low, high = max(1, baseline - 2), min(5, baseline + 2)
    return max(low, min(high, nxt))

def next_mode(
    *,
    answer_score: float,
    specificity: int,
    relevance: int,
    is_empty: bool,
    timed_out: bool,
    clarifications_used: int,
    followups_used: int,
    max_clarifications: int = 1,
    max_followups: int = 2,
) -> Mode:
    """Pick the shape of the next question within the current topic."""
    if is_empty or timed_out:
        return "opening"
    if relevance <= 2 and clarifications_used < max_clarifications:
        return "clarification"
    if specificity <= 2 and followups_used < max_followups:
        return "followup"
    if answer_score >= 4.0 and followups_used < max_followups:
        return "followup"
    return "opening"

def coverage_ratio(covered: int, planned: int) -> float:
    return round(covered / planned, 2) if planned else 0.0

def balance_topic_budgets(
    current_topic_id: str,
    extension_s: int,
    topics: list, 
    min_seconds: int = 100,
) -> tuple[list, int]:

    current_topic = next((t for t in topics if t.id == current_topic_id), None)
    if not current_topic:
        return topics, 0

 

    donors = [t for t in topics if t.id != current_topic_id]
    donors.sort(key=lambda t: t.priority)

    recovered_s = 0
    remaining_to_recover = extension_s

    for donor in donors:
        if remaining_to_recover <= 0:
            break

        reducible = donor.allocated_seconds - min_seconds
        if reducible > 0:
            take = min(reducible, remaining_to_recover)
            donor.allocated_seconds -= take
            recovered_s += take
            remaining_to_recover -= take

    current_topic.allocated_seconds += recovered_s

    return topics, recovered_s

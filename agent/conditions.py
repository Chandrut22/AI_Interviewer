
from typing import Literal

SENIORITY_BASELINE = {
    "intern": 1,
    "entry": 2,
    "junior": 2,
    "mid": 3,
    "mid-level": 3,
    "senior": 4,
    "lead": 4,
    "staff": 5,
    "principal": 5,
    "architect": 5,
}

Mode = Literal["opening", "followup", "clarification"]


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


def topic_difficulty(
    baseline: int, is_claimed_on_resume: bool, is_gap: bool = False
) -> int:
    """Open harder on skills the candidate claims, easier on identified gaps."""
    level = baseline + (1 if is_claimed_on_resume else 0) - (1 if is_gap else 0)
    return max(1, min(5, level))


def adjust_difficulty(current: int, answer_score: float, baseline: int) -> int:
    """Step difficulty after an answer, bounded near the role's baseline."""
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


def depth_credit(answer_score: float, difficulty: int, timed_out: bool) -> int:
    """How much a topic's demonstrated depth advances from one answer.

    Depth is earned, not spent: a confident answer to a level-4 question proves
    more than the same answer to a level-2 one.
    """
    if timed_out or answer_score < 2.5:
        return 0
    if answer_score >= 4.0:
        return 2 if difficulty >= 3 else 1
    return 1





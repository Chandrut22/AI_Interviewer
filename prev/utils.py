from typing import Sequence, Literal
from dataclasses import dataclass

QUESTION_OVERHEAD_S = 12

Action = Literal["continue_topic", "next_topic", "wrap_up"]

@dataclass(frozen=True)
class Pacing:
    action: Action
    reason: str

def allocate_time(
    topics: Sequence[tuple[str, int]],
    total_seconds: int,
    reserve_ratio: float = 0.12,
    min_topic_seconds: int = 150,
) -> tuple[dict[str, int], list[str]]:
    """Split the budget across topics by priority weight.

    Returns (allocation, dropped_topic_ids). Topics are dropped lowest-priority
    first when the budget cannot give every topic `min_topic_seconds` - covering
    four topics properly beats touching nine.
    """
    if not topics or total_seconds <= 0:
        return {}, [tid for tid, _ in topics]

    usable = max(0, int(total_seconds * (1 - reserve_ratio)))
    ordered = sorted(topics, key=lambda t: (-t[1], t[0]))

    keep = list(ordered)
    while len(keep) > 1 and usable // len(keep) < min_topic_seconds:
        keep.pop()
    dropped = [tid for tid, _ in ordered if tid not in {k for k, _ in keep}]

    weight_sum = sum(max(1, w) for _, w in keep) or 1
    raw = {tid: usable * max(1, w) / weight_sum for tid, w in keep}

    floor = min(min_topic_seconds, usable // max(1, len(keep)))
    alloc = {tid: max(float(floor), secs) for tid, secs in raw.items()}

    overflow = sum(alloc.values()) - usable
    if overflow > 0:
        headroom = {tid: alloc[tid] - floor for tid in alloc}
        total_headroom = sum(headroom.values())
        if total_headroom > 0:
            for tid in alloc:
                alloc[tid] -= overflow * (headroom[tid] / total_headroom)

    return {tid: int(round(secs)) for tid, secs in alloc.items()}, dropped

def wrap_up_reserve(total_seconds: int) -> int:
    """Time held back so the interview can close gracefully."""
    return max(60, int(total_seconds * 0.08))

def pace(
    *,
    elapsed_total_s: float,
    total_seconds: int,
    topic_elapsed_s: float,
    topic_allocated_s: int,
    questions_in_topic: int,
    depth_reached: int,
    target_depth: int,
    topics_remaining: int,
) -> Pacing:
    """Decide whether to stay on this topic, move on, or start wrapping up."""
    remaining = total_seconds - elapsed_total_s
    reserve = wrap_up_reserve(total_seconds)

    if remaining <= reserve:
        return Pacing("wrap_up", "Budget exhausted; reserving time to close out.")

    if topics_remaining > 0 and remaining - reserve < topics_remaining * 90:
        if questions_in_topic >= 1:
            return Pacing(
                "next_topic",
                f"Compressing: {int(remaining)}s left for {topics_remaining} "
                "uncovered topic(s).",
            )

    if questions_in_topic == 0:
        return Pacing("continue_topic", "Topic not yet opened.")

    if topic_elapsed_s >= topic_allocated_s:
        action: Action = "next_topic" if topics_remaining > 0 else "wrap_up"
        return Pacing(action, "Topic time budget spent.")

    if depth_reached >= target_depth and questions_in_topic >= 2:
        action = "next_topic" if topics_remaining > 0 else "continue_topic"
        return Pacing(action, f"Target depth {target_depth} reached.")

    if questions_in_topic >= 5:
        action = "next_topic" if topics_remaining > 0 else "wrap_up"
        return Pacing(action, "Question cap for this topic reached.")

    return Pacing("continue_topic", "Time and depth headroom remain on this topic.")

def question_time_limit(
    topic_remaining_s: float,
    expected_questions_left: int = 2,
    floor_s: int = 45,
    ceiling_s: int = 180,
) -> int:
    """Per-question clock, sized so the topic does not overrun its slice."""
    usable = max(0.0, topic_remaining_s - QUESTION_OVERHEAD_S)
    share = usable / max(1, expected_questions_left)
    return int(max(floor_s, min(ceiling_s, share)))


def coverage_ratio(covered: int, planned: int) -> float:
    return round(covered / planned, 2) if planned else 0.0

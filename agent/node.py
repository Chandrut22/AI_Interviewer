from agent.llm import chat_model, structured, get_system_prompt
from agent.prompt import JD_ANALYSIS_SYSTEM, PLAN_TOPICS_SYSTEM, RESUME_ANALYSIS_SYSTEM, QUESTION_MODE_BRIEF, GENERATE_QUESTION_SYSTEM, EVALUATE_ANSWER_SYSTEM, CLASSIFY_RESPONSE_SYSTEM, DECIDE_NEXT_SYSTEM
from datetime import datetime
from agent.state import InterviewState, JDAnalysis, ResumeAnalysis, TopicPlan, TopicRun, Event, Question, Evaluation, Discrepancy, ResponseClassification, NextActionDecision
from agent.utils import wrap_up_reserve, baseline_difficulty, topic_difficulty, depth_credit, adjust_difficulty, next_mode, balance_topic_budgets
from dotenv import load_dotenv
from langgraph.types import interrupt
import os

load_dotenv()
DEFAULT_QUESTION_SECONDS = int(os.getenv("DEFAULT_QUESTION_SECONDS", 120))
MIN_QUESTION_SECONDS = 45
DOUBT_THRESHOLD = int(os.getenv("DOUBT_THRESHOLD", 2))
MIN_TOPIC_SECONDS = int(os.getenv("MIN_TOPIC_SECONDS", 150))
PLAN_FIX_ATTEMPTS = int(os.getenv("PLAN_FIX_ATTEMPTS", 2))

def analyze_jd(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    jd = structured(
        llm,
        JDAnalysis,
        system=get_system_prompt("JD_ANALYSIS_SYSTEM", JD_ANALYSIS_SYSTEM),
        user=state["jd_text"],
    )
    return {"jd_analysis": jd}

def analyze_resume(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    resume = structured(
        llm,
        ResumeAnalysis,
        system=get_system_prompt("RESUME_ANALYSIS_SYSTEM", RESUME_ANALYSIS_SYSTEM),
        user=state["resume_text"],
    )
    return {"resume_analysis": resume}


def _suggested_topics() -> str:
    raw = os.getenv("TOPICS_COVER_SUGGESTION", "").strip()
    return "none" if raw.lower() in ("", "all", "none") else raw


def _plan_errors(plan: TopicPlan, allocatable: int) -> list[str]:
    """Exact checks the plan_topics prompt promises the model."""
    errors: list[str] = []
    topics = [t for t in plan.topics if t.id]
    if not topics:
        return ["`topics` is empty; keep at least one topic."]

    ids = [t.id for t in topics]
    if len(ids) != len(set(ids)):
        errors.append("Topic ids must be unique.")
    both = set(ids) & {d.id for d in plan.dropped}
    if both:
        errors.append(f"Topics listed in both `topics` and `dropped`: {', '.join(sorted(both))}.")

    total = sum(t.allocated_seconds for t in topics)
    if total != allocatable:
        errors.append(f"allocated_seconds sums to {total}, but must equal exactly {allocatable}.")
    if plan.total_allocated_seconds != total:
        errors.append(f"`total_allocated_seconds` is {plan.total_allocated_seconds}, but the topics sum to {total}.")

    for t in topics:
        if t.allocated_seconds < MIN_TOPIC_SECONDS:
            errors.append(f"'{t.id}' has {t.allocated_seconds}s, below the {MIN_TOPIC_SECONDS}s minimum; raise it or move it to `dropped`.")

    for hi in topics:
        for lo in topics:
            if hi.priority > lo.priority and hi.allocated_seconds < lo.allocated_seconds and not hi.is_gap:
                errors.append(f"'{hi.id}' (priority {hi.priority}) has less time than '{lo.id}' (priority {lo.priority}).")
    return errors


def plan_topics(state: InterviewState) -> dict:
    """LLM selects topics AND calculates their timing; the arithmetic is checked here. Runs once, checkpointed."""
    llm = chat_model(temperature=0.5)
    jd, resume = state["jd_analysis"], state["resume_analysis"]
    total_seconds = state["total_seconds"]
    reserve = wrap_up_reserve(total_seconds)
    allocatable = total_seconds - reserve
    max_topics = max(1, allocatable // MIN_TOPIC_SECONDS)

    system = get_system_prompt(
        "PLAN_TOPICS_SYSTEM", PLAN_TOPICS_SYSTEM,
        seniority=jd.seniority, role_title=jd.role_title,
        total_seconds=total_seconds, total_minutes=total_seconds // 60,
        reserve_seconds=reserve, allocatable_seconds=allocatable,
        min_topic_seconds=MIN_TOPIC_SECONDS, max_topics=max_topics,
    )
    user = (
        f"SUGGESTED TOPICS: {_suggested_topics()}\n\n"
        f"JOB REQUIREMENTS:\n{jd.model_dump_json(indent=2)}\n\n"
        f"RESUME CLAIMS:\n{resume.model_dump_json(indent=2)}"
    )

    plan = structured(llm, TopicPlan, system=system, user=user)
    errors = _plan_errors(plan, allocatable)
    for _ in range(PLAN_FIX_ATTEMPTS):
        if not errors:
            break
        plan = structured(
            llm, TopicPlan, system=system,
            user=(
                f"{user}\n\nYOUR PREVIOUS PLAN:\n{plan.model_dump_json(indent=2)}\n\n"
                "It failed these checks:\n- " + "\n- ".join(errors) +
                "\n\nReturn the full corrected plan."
            ),
        )
        errors = _plan_errors(plan, allocatable)
    if errors:
        # Human approval step can still override the allocation.
        print("Warning: topic plan still fails checks:\n- " + "\n- ".join(errors))

    kept = [t for t in plan.topics if t.id and t.allocated_seconds > 0]
    if not kept:
        raise ValueError("Topic planner did not allocate time to any topic")

    kept.sort(key=lambda topic: topic.priority, reverse=True)
    dropped = [d.id for d in plan.dropped] + [
        t.id for t in plan.topics if t.id and t.allocated_seconds <= 0
    ]

    return {"topics": kept, "dropped_topics": dropped}


def approve_time_allocation(state: InterviewState) -> dict:
    """Pure Python, no LLM calls - safe to replay across interrupts/resumes."""
    jd = state["jd_analysis"]
    total_seconds = state["total_seconds"]
    kept = state["topics"]
    dropped = state.get("dropped_topics", [])
    llm_allocation = {t.id: t.allocated_seconds for t in kept}

    approval = interrupt({
        "type": "time_allocation_approval",
        "topics": [
            {"id": t.id, "name": t.name, "priority": t.priority,
             "allocated_seconds": llm_allocation[t.id]} for t in kept
        ],
        "dropped_for_time": dropped,
        "total_seconds": total_seconds,
    })

    if isinstance(approval, dict):
        is_approved = approval.get("approved", False)
    elif isinstance(approval, str):
        is_approved = approval.strip().lower() in ["yes", "true", "approve", "approved", "y"]
    else:
        is_approved = False

    if is_approved:
        allocation = llm_allocation
    else:
        allocation = {}
        for topic in kept:
            resp = interrupt({
                "type": "time_allocation_input",
                "topic_id": topic.id,
                "topic_name": topic.name,
                "priority": topic.priority,
                "suggested_seconds": llm_allocation[topic.id],
                "total_seconds": total_seconds,
                "allocated_so_far": sum(allocation.values()),
            })
            allocation[topic.id] = int(resp.get("seconds", llm_allocation[topic.id]))

    base = baseline_difficulty(jd.seniority, jd.years_required)

    runs: dict[str, TopicRun] = {}
    for topic in kept:
        topic.allocated_seconds = allocation[topic.id]
        runs[topic.id] = TopicRun(
                difficulty=topic_difficulty(base, topic.claimed_on_resume, topic.is_gap)
        )

    order = [t.id for t in kept]

    start = Event(
            kind="interview_start",
            t_offset_s=0.0,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            text=f"{jd.role_title} ({jd.seniority}) - {total_seconds // 60} minute budget",
            meta={
                "topics": {t.id: t.allocated_seconds for t in kept},
                "dropped_for_time": dropped,
                "baseline_difficulty": base,
            },
        )

    return {
            "topics": kept,
            "dropped_topics": dropped,
            "topic_runs": runs,
            "topic_order": order,
            "current_topic_id": order[0] if order else None,
            "next_mode": "opening",
            "elapsed_s": 0.0,
            "question_counter": 0,
            "doubt_count": 0,
            "completion_status": "in_progress",
            "transcript": [start],
        }

def _event(kind: str, state: InterviewState, **kwargs) -> Event:
    return Event(
        kind=kind,
        t_offset_s=round(state.get("elapsed_s", 0.0), 1),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        **kwargs,
    )

def decide_next(state: InterviewState) -> dict:
    """Evaluate the latest response, rebalance topic time, and choose the next action."""

    order = state["topic_order"]

    runs = {
        tid: run.model_copy(deep=True)
        for tid, run in state["topic_runs"].items()
    }

    topics = [topic.model_copy(deep=True) for topic in state["topics"]]
    topic_by_id = {topic.id: topic for topic in topics}

    current = state.get("current_topic_id")

    events: list[Event] = []
    discrepancies = list(state.get("discrepancies", []))


    if current is None or current not in topic_by_id or current not in runs:
        return {
            "topics": topics,
            "topic_runs": runs,
            "next_action": "wrap_up",
            "pacing_note": "No valid current topic to cover.",
            "last_response_type": None,
        }

    question = state.get("pending_question")

    answer_event = next(
        (
            event
            for event in reversed(state.get("transcript", []))
            if event.kind == "answer"
        ),
        None,
    )

    response_type = None
    selected_next_mode = state.get("next_mode", "opening")
    evaluation = None


    force_next_topic = False

    if answer_event is not None and question is not None:
        answer = answer_event.text or ""
        timed_out = bool(answer_event.meta.get("timed_out"))

        topic = topic_by_id[current]
        run = runs[current]

        if not answer.strip():
            evaluation = Evaluation(
                relevance=1,
                depth=1,
                specificity=1,
                correctness=1,
                communication=1,
                verdict="No answer given within the time limit.",
                gap_note=f"No response on {topic.name}.",
                needs_validation=True,
            )

            selected_next_mode = "opening"

        else:
           
            llm = chat_model(temperature=0.1)

            classification = structured(
                llm,
                ResponseClassification,
                system=get_system_prompt(
                    "CLASSIFY_RESPONSE_SYSTEM",
                    CLASSIFY_RESPONSE_SYSTEM,
                ),
                user=(
                    f"QUESTION: {question.text}\n"
                    f"ANSWER: {answer}"
                ),
            )


            if classification.classification == "skip_topic":
                force_next_topic = True
                response_type = "skip_topic"
                selected_next_mode = "opening"

                events.append(
                    _event(
                        "evaluation",
                        state,
                        topic_id=current,
                        question_id=question.id,
                        text=(
                            "Candidate requested to skip the current topic."
                        ),
                        meta={
                            "outcome": "topic_skipped",
                            "classification": "skip_topic",
                        },
                    )
                )

            elif classification.classification == "doubt":
                doubt_count = state.get("doubt_count", 0)

                if doubt_count < DOUBT_THRESHOLD:
                    return {
                        "topics": topics,
                        "topic_runs": runs,
                        "doubt_count": doubt_count + 1,
                        "next_action": "ask",
                        "next_mode": "clarification",
                        "last_response_type": "doubt",
                        "pacing_note": (
                            f"Clarifying doubt ({doubt_count + 1}/"
                            f"{DOUBT_THRESHOLD})"
                        ),
                    }

                events.append(
                    _event(
                        "evaluation",
                        state,
                        topic_id=current,
                        question_id=question.id,
                        text=(
                            "Doubt threshold reached; moving to a new question."
                        ),
                        meta={
                            "outcome": "doubt_threshold_exceeded",
                        },
                    )
                )

                return {
                    "topics": topics,
                    "topic_runs": runs,
                    "transcript": events,
                    "next_action": "ask",
                    "next_mode": "opening",
                    "last_response_type": "doubt",
                    "pacing_note": (
                        "Doubt threshold reached; asking a new question."
                    ),
                }

            else:
                try:
                    evaluation = structured(
                        llm,
                        Evaluation,
                        system=get_system_prompt(
                            "EVALUATE_ANSWER_SYSTEM",
                            EVALUATE_ANSWER_SYSTEM,
                        ),
                        user=(
                            f"TOPIC: {topic.name}\n"
                            f"RESUME CLAIM ON THIS TOPIC: "
                            f"{topic.resume_evidence or 'none'}\n"
                            f"QUESTION (difficulty {question.difficulty}/5, "
                            f"mode {question.mode}): {question.text}\n"
                            f"STRONG ANSWER CONTAINS: {question.looking_for}\n"
                            f"ANSWER: {answer}\n"
                            f"TIME: used "
                            f"{answer_event.meta.get('answer_s')}s of "
                            f"{question.time_limit_s}s"
                            f"{'; ran out of time, may be cut off' if timed_out else ''}"
                        ),
                    )

                except ValueError:
                    evaluation = Evaluation(
                        relevance=3,
                        depth=3,
                        specificity=3,
                        correctness=3,
                        communication=3,
                        verdict=(
                            "Answer could not be scored automatically; "
                            "needs human review."
                        ),
                        gap_note=(
                            f"Scoring failed on {topic.name}; see transcript."
                        ),
                        needs_validation=True,
                    )

        if evaluation is not None:
            evaluation.question_id = question.id
            evaluation.topic_id = topic.id

            if evaluation.depth <= 1:
                run.consecutive_low_depth_answers += 1
            else:
                run.consecutive_low_depth_answers = 0

            if not answer.strip():
                run.scores.append(evaluation.overall)

                events.append(
                    _event(
                        "evaluation",
                        state,
                        topic_id=topic.id,
                        question_id=question.id,
                        text=evaluation.verdict,
                        meta={
                            "overall": evaluation.overall,
                            "next_mode": selected_next_mode,
                        },
                    )
                )

            else:
                score = evaluation.overall

                run.scores.append(score)

                run.depth_reached = min(
                    5,
                    run.depth_reached
                    + depth_credit(
                        score,
                        question.difficulty,
                        timed_out,
                    ),
                )

                previous_difficulty = run.difficulty

                run.difficulty = adjust_difficulty(
                    previous_difficulty,
                    score,
                    baseline_difficulty(
                        state["jd_analysis"].seniority,
                        state["jd_analysis"].years_required,
                    ),
                )

                selected_next_mode = next_mode(
                    answer_score=score,
                    specificity=evaluation.specificity,
                    relevance=evaluation.relevance,
                    is_empty=not answer.strip(),
                    timed_out=timed_out,
                    clarifications_used=run.clarifications_used,
                    followups_used=run.followups_used,
                )

                events.append(
                    _event(
                        "evaluation",
                        state,
                        topic_id=topic.id,
                        question_id=question.id,
                        text=evaluation.verdict,
                        meta={
                            "overall": score,
                            "depth_reached": run.depth_reached,
                            "next_mode": selected_next_mode,
                        },
                    )
                )

                # Record difficulty adjustment.
                if run.difficulty != previous_difficulty:
                    direction = (
                        "up"
                        if run.difficulty > previous_difficulty
                        else "down"
                    )

                    events.append(
                        _event(
                            "difficulty_change",
                            state,
                            topic_id=topic.id,
                            text=(
                                f"Difficulty {direction}: "
                                f"{previous_difficulty} "
                                f"-> {run.difficulty}"
                            ),
                            meta={
                                "from": previous_difficulty,
                                "to": run.difficulty,
                            },
                        )
                    )

                if evaluation.contradicts_resume:
                    discrepancies.append(
                        Discrepancy(
                            topic_id=topic.id,
                            resume_claim="; ".join(
                                topic.resume_evidence
                            )[:300],
                            answer_signal=evaluation.verdict,
                            note=evaluation.discrepancy_note,
                        )
                    )

            response_type = "answer"


    if (
        response_type == "answer"
        and evaluation is not None
        and evaluation.overall >= 4.0
    ):
        topic = topic_by_id[current]
        run = runs[current]

        allocated = topic.allocated_seconds

        if allocated > 0 and run.elapsed_s >= 0.9 * allocated:
            extension_s = 60

            updated_topics, recovered_s = balance_topic_budgets(
                current_topic_id=current,
                extension_s=extension_s,
                topics=topics,
                topic_runs=runs,
                min_seconds=MIN_TOPIC_SECONDS,
            )


            topics = updated_topics
            topic_by_id = {
                item.id: item
                for item in topics
            }

            if recovered_s > 0:
                events.append(
                    _event(
                        "time_adjustment",
                        state,
                        topic_id=current,
                        text=(
                            f"Dynamic extension: +{recovered_s}s allocated "
                            f"to {topic_by_id[current].name}, recovered from "
                            "eligible lower-priority pending topics."
                        ),
                        meta={
                            "recovered_s": recovered_s,
                        },
                    )
                )

    remaining_topics = [
        tid
        for tid in order
        if (
            tid in runs
            and runs[tid].status == "pending"
            and tid != current
        )
    ]

    current_topic = topic_by_id[current]
    current_run = runs[current]

    
    # Condition 1: Current topic's allocated time is exhausted.
    time_limit_reached = (
        current_topic.allocated_seconds > 0
        and current_run.elapsed_s >= current_topic.allocated_seconds
    )

    # Condition 2: Candidate reached the topic's target depth.
    # For a 5/5 target, this triggers when depth_reached >= 5.
    target_depth_reached = (
        current_run.depth_reached >= current_topic.target_depth
    )

    # Condition 3: Two consecutive low-depth evaluations.
    low_depth_reached = (
        current_run.consecutive_low_depth_answers >= 2
    )

    # Explicit skip request has the highest priority.
    if force_next_topic:
        action = "next_topic"
        reason = "Candidate requested to skip the current topic."

    elif time_limit_reached:
        action = "next_topic"
        reason = (
            f"Time limit reached for {current_topic.name} "
            f"({current_run.elapsed_s:.0f}/"
            f"{current_topic.allocated_seconds}s)."
        )

    elif target_depth_reached:
        action = "next_topic"
        reason = (
            f"Target depth reached for {current_topic.name} "
            f"({current_run.depth_reached}/"
            f"{current_topic.target_depth})."
        )

    elif low_depth_reached:
        action = "next_topic"
        reason = (
            f"Moving on from {current_topic.name}: "
            "candidate received depth 1 on two consecutive answers."
        )


    else:
        llm = chat_model(temperature=0.1)

        decision = structured(
            llm,
            NextActionDecision,
            system=get_system_prompt(
                "DECIDE_NEXT_SYSTEM",
                DECIDE_NEXT_SYSTEM,
            ),
            user=(
                f"GLOBAL BUDGET: {state.get('elapsed_s', 0.0)}s / "
                f"{state['total_seconds']}s\n"
                f"TOPIC METRICS: {current_topic.name} | "
                f"Budget: {current_topic.allocated_seconds}s | "
                f"Elapsed: {current_run.elapsed_s}s | "
                f"Questions: {current_run.questions_asked} | "
                f"Depth: {current_run.depth_reached}/"
                f"{current_topic.target_depth}\n"
                f"PERFORMANCE: Mean Score: {current_run.mean_score}\n"
                f"PROGRESS: Topics remaining: {len(remaining_topics)}"
            ),
        )

        action = decision.action
        reason = decision.reasoning

    if action == "wrap_up":
        if current_run.status == "active":
            current_run.status = (
                "covered"
                if current_run.questions_asked
                else "skipped"
            )

            events.append(
                _event(
                    "topic_end",
                    state,
                    topic_id=current,
                    text=reason,
                )
            )

        # Mark all remaining pending topics as skipped.
        for topic_id in remaining_topics:
            runs[topic_id].status = "skipped"

        return {
            "topics": topics,
            "topic_runs": runs,
            "discrepancies": discrepancies,
            "next_action": "wrap_up",
            "pacing_note": reason,
            "transcript": events,
            "last_response_type": None,
        }


    if action == "next_topic":
        # Transfer unused time to the next pending topic before closing this one.
        # This preserves the total interview budget while rewarding early completion.
        next_topic_id = remaining_topics[0] if remaining_topics else None
        unused_seconds = 0

        if next_topic_id is not None and current_topic.allocated_seconds > 0:
            unused_seconds = max(
                0,
                int(current_topic.allocated_seconds - current_run.elapsed_s),
            )

            if unused_seconds > 0:
                reduced_current_allocation = max(
                    0,
                    int(current_run.elapsed_s),
                )
                next_topic = topic_by_id[next_topic_id]

                # Use model_copy so this works even with frozen Pydantic models.
                updated_current_topic = current_topic.model_copy(
                    update={"allocated_seconds": reduced_current_allocation}
                )
                updated_next_topic = next_topic.model_copy(
                    update={
                        "allocated_seconds": (
                            next_topic.allocated_seconds + unused_seconds
                        )
                    }
                )

                topics = [
                    updated_current_topic if item.id == current else
                    updated_next_topic if item.id == next_topic_id else
                    item
                    for item in topics
                ]
                topic_by_id = {item.id: item for item in topics}
                current_topic = topic_by_id[current]

                events.append(
                    _event(
                        "time_adjustment",
                        state,
                        topic_id=next_topic_id,
                        text=(
                            f"Transferred {unused_seconds}s of unused time "
                            f"from {current_topic.name} to "
                            f"{topic_by_id[next_topic_id].name}."
                        ),
                        meta={
                            "transfer_s": unused_seconds,
                            "from_topic_id": current,
                            "to_topic_id": next_topic_id,
                        },
                    )
                )

        # Explicit skips and repeated low-depth answers are recorded as skipped.
        was_skipped = force_next_topic or low_depth_reached
        current_run.status = (
            "skipped"
            if was_skipped
            else "covered" if current_run.questions_asked else "skipped"
        )

        events.append(
            _event(
                "topic_end",
                state,
                topic_id=current,
                text=reason,
                meta={
                    "depth_reached": current_run.depth_reached,
                    "mean_score": current_run.mean_score,
                    "outcome": (
                        "candidate_requested_skip"
                        if force_next_topic
                        else "low_depth_skip"
                        if low_depth_reached
                        else "topic_completed"
                    ),
                },
            )
        )

        # Select the next pending topic in the original plan order.
        current = (
            remaining_topics[0]
            if remaining_topics
            else None
        )

        # No topics remain, so wrap up.
        if current is None:
            return {
                "topics": topics,
                "topic_runs": runs,
                "discrepancies": discrepancies,
                "next_action": "wrap_up",
                "pacing_note": "All topics covered.",
                "transcript": events,
                "last_response_type": None,
            }

        current_topic = topic_by_id[current]
        current_run = runs[current]

    # ---------------------------------------------------------
    # PHASE F: Activate the selected topic.
    # ---------------------------------------------------------

    if current_run.status == "pending":
        current_run.status = "active"

        events.append(
            _event(
                "topic_start",
                state,
                topic_id=current,
                text=current_topic.name,
                meta={
                    "priority": current_topic.priority,
                    "allocated_s": current_topic.allocated_seconds,
                    "target_depth": current_topic.target_depth,
                    "difficulty": current_run.difficulty,
                    "is_gap": current_topic.is_gap,
                },
            )
        )

    # A newly selected topic always starts with an opening question.
    mode = selected_next_mode

    if current != state.get("current_topic_id"):
        mode = "opening"

    # ---------------------------------------------------------
    # PHASE G: Return updated interview state.
    # ---------------------------------------------------------

    return {
        "topics": topics,
        "topic_runs": runs,
        "discrepancies": discrepancies,
        "current_topic_id": current,
        "next_mode": mode,
        "next_action": "ask",
        "pacing_note": reason,
        "transcript": events,
        "last_response_type": response_type,
    }


def route(state: InterviewState) -> str:
    return "generate_question" if state.get("next_action") == "ask" else "build_report"



def generate_question(state: InterviewState) -> dict:
    topic = next(t for t in state["topics"] if t.id == state["current_topic_id"])
    run = state["topic_runs"][topic.id]
    mode = state.get("next_mode", "opening")
    counter = state.get("question_counter", 0) + 1

    per_question = topic.seconds_per_question or DEFAULT_QUESTION_SECONDS
    topic_remaining = topic.allocated_seconds - run.elapsed_s
    limit = int(max(MIN_QUESTION_SECONDS, min(per_question, topic_remaining)))

    history = "\n".join(
        f"{e.kind.upper()}: {e.text}"
        for e in state.get("transcript", [])
        if e.topic_id == topic.id and e.kind in {"question", "answer"}
    )[-3000:]

    doubt_context = ""
    if state.get("last_response_type") == "doubt":
        doubt_event = next(
            (e for e in reversed(state.get("transcript", [])) if e.kind == "answer"),
            None
        )
        if doubt_event:
            doubt_context = f"\n\nCANDIDATE'S DOUBT:\n{doubt_event.text}\n"

    mode_brief = QUESTION_MODE_BRIEF[mode]

    llm = chat_model(temperature=0.6)
    question = structured(
        llm,
        Question,
        system=get_system_prompt(
            "GENERATE_QUESTION_SYSTEM", GENERATE_QUESTION_SYSTEM,
            difficulty=run.difficulty, mode_brief=mode_brief,
        ),
        user=(
            f"ROLE: {state['jd_analysis'].seniority} "
            f"{state['jd_analysis'].role_title}\n"
            f"TOPIC: {topic.name} ({topic.rationale})\n"
            f"RESUME EVIDENCE: {topic.resume_evidence or 'none - probe carefully'}\n"
            f"IS IDENTIFIED GAP: {topic.is_gap}\n"
            f"TIME LIMIT: {limit}s\n"
            f"THIS TOPIC SO FAR:\n{history or '(nothing yet)'}"
            f"{doubt_context}"
        ),
    )
    question.id = f"q{counter}"
    question.topic_id = topic.id
    question.mode = mode
    question.difficulty = run.difficulty
    question.time_limit_s = limit

    return {
        "pending_question": question,
        "question_counter": counter,
        "last_response_type": None, 
        "transcript": [
            _event("question", state, topic_id=topic.id, question_id=question.id,
                   text=question.text,
                   meta={"mode": mode, "difficulty": run.difficulty,
                         "time_limit_s": limit, "looking_for": question.looking_for})
        ],
    }


def ask_question(state: InterviewState) -> dict:
    question = state["pending_question"]
    topic = next(t for t in state["topics"] if t.id == question.topic_id)
    run = state["topic_runs"][topic.id]

    reply = interrupt(
        {
            "type": "question",
            "question_id": question.id,
            "text": question.text,
            "clarification": question.clarification,
            "mode": question.mode,
            "difficulty": question.difficulty,
            "time_limit_s": question.time_limit_s,
            "topic": topic.name,
            "topic_id": topic.id,
            "topic_index": state["topic_order"].index(topic.id) + 1,
            "topic_total": len(state["topic_order"]),
            "questions_asked": run.questions_asked + 1,
            "clarifications_used": run.clarifications_used,
            "doubt_count": state.get("doubt_count", 0),
            "doubts_remaining": max(0, DOUBT_THRESHOLD - state.get("doubt_count", 0)),
            "elapsed_s": round(state.get("elapsed_s", 0.0)),
            "total_seconds": state["total_seconds"],
            "pacing_note": state.get("pacing_note", ""),
        }
    )

    answer = reply.get("answer", "")
    spent = float(reply.get("elapsed_s", 0.0))
    elapsed = state.get("elapsed_s", 0.0) + spent

    runs = {tid: r.model_copy() for tid, r in state["topic_runs"].items()}
    run = runs[topic.id]
    run.elapsed_s += spent
    run.questions_asked += 1
    if question.mode == "followup":
        run.followups_used += 1
    elif question.mode == "clarification":
        run.clarifications_used += 1

    return {
        "topic_runs": runs,
        "elapsed_s": elapsed,
        "transcript": [
            Event(
                kind="answer",
                t_offset_s=round(elapsed, 1),
                timestamp=datetime.now().isoformat(timespec="seconds"),
                topic_id=topic.id,
                question_id=question.id,
                text=answer,
                meta={
                    "answer_s": round(float(reply.get("elapsed_s", 0.0)), 1),
                    "timed_out": bool(reply.get("timed_out", False)),
                },
            )
        ],
    }


from agent.llm import chat_model, structured, get_system_prompt
from agent.prompt import JD_ANALYSIS_SYSTEM, PLAN_TOPICS_SYSTEM, RESUME_ANALYSIS_SYSTEM, QUESTION_MODE_BRIEF, GENERATE_QUESTION_SYSTEM
from datetime import datetime
from agent.state import InterviewState, JDAnalysis, ResumeAnalysis, TopicPlan, TopicRun, Event, Question
from agent.utils import wrap_up_reserve, baseline_difficulty, topic_difficulty
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

    # doubt_context = ""
    # if state.get("last_response_type") == "doubt":
    #     doubt_event = next(
    #         (e for e in reversed(state.get("transcript", [])) if e.kind == "answer"),
    #         None
    #     )
    #     if doubt_event:
    #         doubt_context = f"\n\nCANDIDATE'S DOUBT:\n{doubt_event.text}\n"

    mode_brief = QUESTION_MODE_BRIEF[mode]

    focus = (state.get("question_focus") or "").strip()
    focus_context = f"\n\nINTERVIEWER FOCUS FOR THIS QUESTION:\n{focus}\n" if focus else ""

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
            f"{focus_context}"
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

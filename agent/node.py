


from agent.llm import chat_model, structured
from agent.prompt import JD_ANALYSIS_SYSTEM, PLAN_TOPICS_SYSTEM, RESUME_ANALYSIS_SYSTEM, QUESTION_MODE_BRIEF, GENERATE_QUESTION_SYSTEM, EVALUATE_ANSWER_SYSTEM
from datetime import datetime
from agent.state import InterviewState, JDAnalysis, ResumeAnalysis, TopicPlan, TopicRun, Event, Question, Evaluation, Discrepancy
from agent.utils import baseline_difficulty, allocate_time, topic_difficulty, pace, question_time_limit, depth_credit, adjust_difficulty, next_mode
from dotenv import load_dotenv
from langgraph.types import interrupt
import os


load_dotenv()
MAX_QUESTIONS_IN_TOPIC = int(os.getenv("MAX_QUESTIONS_IN_TOPIC", 4))

def analyze_jd(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    jd = structured(
        llm,
        JDAnalysis,
        system=JD_ANALYSIS_SYSTEM,
        user=state["jd_text"],
    )
    return {"jd_analysis": jd}

def analyze_resume(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    resume = structured(
        llm,
        ResumeAnalysis,
        system=RESUME_ANALYSIS_SYSTEM,
        user=state["resume_text"],
    )
    return {"resume_analysis": resume}


def plan_topics(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.5)
    jd, resume = state["jd_analysis"], state["resume_analysis"]
    total_seconds = state["total_seconds"]
    suggested = os.getenv("TOPICS_COVER_SUGGESTION","all")

    plan = structured(
        llm,
        TopicPlan,
        system=PLAN_TOPICS_SYSTEM.format(
            suggested=suggested, seniority=jd.seniority, role_title=jd.role_title
        ),
        user=(
            f"JOB REQUIREMENTS:\n{jd.model_dump_json(indent=2)}\n\n"
            f"RESUME CLAIMS:\n{resume.model_dump_json(indent=2)}"
        ),
    )

    topics = [t for t in plan.topics if t.id]
    if not topics:
        raise ValueError("Topic planner returned no usable topics")

    allocation, dropped = allocate_time(
            [(t.id, t.priority) for t in topics], total_seconds
    )

    kept = [t for t in topics if t.id in allocation]
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
    
    order = state["topic_order"]
    runs = {tid: run.model_copy() for tid, run in state["topic_runs"].items()}
    topics = {t.id: t for t in state["topics"]}
    current = state.get("current_topic_id")
    events: list[Event] = []

    if current is None:
        return {"next_action": "wrap_up", "pacing_note": "No topics to cover."}

    remaining_after_current = [
        tid for tid in order if runs[tid].status == "pending" and tid != current
    ]
    run, topic = runs[current], topics[current]

    decision = pace(
        elapsed_total_s=state.get("elapsed_s", 0.0),
        total_seconds=state["total_seconds"],
        topic_elapsed_s=run.elapsed_s,
        topic_allocated_s=topic.allocated_seconds,
        questions_in_topic=run.questions_asked,
        depth_reached=run.depth_reached,
        target_depth=topic.target_depth,
        topics_remaining=len(remaining_after_current),
    )

    if decision.action == "wrap_up":
        if run.status == "active":
            run.status = "covered" if run.questions_asked else "skipped"
            events.append(
                _event("topic_end", state, topic_id=current, text=decision.reason)
            )
        for tid in remaining_after_current:
            runs[tid].status = "skipped"
        return {
            "topic_runs": runs,
            "next_action": "wrap_up",
            "pacing_note": decision.reason,
            "transcript": events,
        }

    if decision.action == "next_topic":
        run.status = "covered" if run.questions_asked else "skipped"
        events.append(
            _event("topic_end", state, topic_id=current, text=decision.reason,
                   meta={"depth_reached": run.depth_reached,
                         "mean_score": run.mean_score})
        )
        current = remaining_after_current[0]
        run, topic = runs[current], topics[current]

    if run.status == "pending":
        run.status = "active"
        events.append(
            _event("topic_start", state, topic_id=current,
                   text=topic.name,
                   meta={"priority": topic.priority,
                         "allocated_s": topic.allocated_seconds,
                         "target_depth": topic.target_depth,
                         "difficulty": run.difficulty,
                         "is_gap": topic.is_gap})
        )

    mode = state.get("next_mode", "opening")
    if current != state.get("current_topic_id"):
        mode = "opening"

    return {
        "topic_runs": runs,
        "current_topic_id": current,
        "next_mode": mode,
        "next_action": "ask",
        "pacing_note": decision.reason,
        "transcript": events,
    }


def route(state: InterviewState) -> str:
    return "generate_question" if state.get("next_action") == "ask" else "build_report"



def generate_question(state: InterviewState) -> dict:
    topic = next(t for t in state["topics"] if t.id == state["current_topic_id"])
    run = state["topic_runs"][topic.id]
    mode = state.get("next_mode", "opening")
    counter = state.get("question_counter", 0) + 1

    topic_remaining = max(30.0, topic.allocated_seconds - run.elapsed_s)
    limit = question_time_limit(topic_remaining,max(0, MAX_QUESTIONS_IN_TOPIC - run.questions_asked))

    history = "\n".join(
        f"{e.kind.upper()}: {e.text}"
        for e in state.get("transcript", [])
        if e.topic_id == topic.id and e.kind in {"question", "answer"}
    )[-3000:]

    mode_brief = QUESTION_MODE_BRIEF[mode]

    llm = chat_model(temperature=0.6)
    question = structured(
        llm,
        Question,
        system=GENERATE_QUESTION_SYSTEM.format(
            difficulty=run.difficulty, mode_brief=mode_brief
        ),
        user=(
            f"ROLE: {state['jd_analysis'].seniority} "
            f"{state['jd_analysis'].role_title}\n"
            f"TOPIC: {topic.name} ({topic.rationale})\n"
            f"RESUME EVIDENCE: {topic.resume_evidence or 'none - probe carefully'}\n"
            f"IS IDENTIFIED GAP: {topic.is_gap}\n"
            f"TIME LIMIT: {limit}s\n"
            f"THIS TOPIC SO FAR:\n{history or '(nothing yet)'}"
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
            "question_id": question.id,
            "text": question.text,
            "mode": question.mode,
            "difficulty": question.difficulty,
            "time_limit_s": question.time_limit_s,
            "topic": topic.name,
            "topic_id": topic.id,
            "topic_index": state["topic_order"].index(topic.id) + 1,
            "topic_total": len(state["topic_order"]),
            "questions_in_topic": run.questions_asked + 1,
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

def evaluate_answer(state: InterviewState) -> dict:
    question = state["pending_question"]
    answer_event = next(
        e for e in reversed(state["transcript"]) if e.kind == "answer"
    )
    answer = answer_event.text
    timed_out = bool(answer_event.meta.get("timed_out"))
    topic = next(t for t in state["topics"] if t.id == question.topic_id)
    runs = {tid: r.model_copy() for tid, r in state["topic_runs"].items()}
    run = runs[topic.id]

    if answer.strip():
        llm = chat_model(temperature=0.2)
        try:
            ev = structured(
                llm,
                Evaluation,
                system=EVALUATE_ANSWER_SYSTEM,
                user=(
                    f"TOPIC: {topic.name}\n"
                    f"RESUME CLAIM ON THIS TOPIC: {topic.resume_evidence or 'none'}\n"
                    f"QUESTION (difficulty {question.difficulty}/5, "
                    f"mode {question.mode}): {question.text}\n"
                    f"STRONG ANSWER CONTAINS: {question.looking_for}\n"
                    f"ANSWER: {answer}\n"
                    f"TIME: used {answer_event.meta.get('answer_s')}s of "
                    f"{question.time_limit_s}s"
                    f"{'; ran out of time, may be cut off' if timed_out else ''}"
                ),
            )
        except ValueError:

            ev = Evaluation(
                relevance=3, depth=3, specificity=3, correctness=3, communication=3,
                verdict="Answer could not be scored automatically; needs human review.",
                gap_note=f"Scoring failed on {topic.name}; see transcript.",
                needs_validation=True,
            )
    else:
        ev = Evaluation(
            relevance=1, depth=1, specificity=1, correctness=1, communication=1,
            verdict="No answer given within the time limit.",
            gap_note=f"No response on {topic.name}.",
            needs_validation=True,
        )
    ev.question_id = question.id
    ev.topic_id = topic.id

    score = ev.overall
    run.scores.append(score)
    run.depth_reached = min(
        5, run.depth_reached + depth_credit(score, question.difficulty, timed_out)
    )
    previous = run.difficulty
    run.difficulty = adjust_difficulty(
        previous, score, baseline_difficulty(
            state["jd_analysis"].seniority, state["jd_analysis"].years_required
        )
    )

    mode = next_mode(
        answer_score=score,
        specificity=ev.specificity,
        relevance=ev.relevance,
        is_empty=not answer.strip(),
        timed_out=timed_out,
        clarifications_used=run.clarifications_used,
        followups_used=run.followups_used,
    )

    events = [
        _event("evaluation", state, topic_id=topic.id, question_id=question.id,
               text=ev.verdict,
               meta={"overall": score, "depth_reached": run.depth_reached,
                     "next_mode": mode})
    ]
    if run.difficulty != previous:
        direction = "up" if run.difficulty > previous else "down"
        events.append(
            _event("difficulty_change", state, topic_id=topic.id,
                   text=f"Difficulty {direction}: {previous} -> {run.difficulty}",
                   meta={"from": previous, "to": run.difficulty})
        )

    out: dict = {
        "topic_runs": runs,
        "evaluations": [ev],
        "next_mode": mode,
        "transcript": events,
    }
    if ev.contradicts_resume:
        out["discrepancies"] = [
            Discrepancy(
                topic_id=topic.id,
                resume_claim="; ".join(topic.resume_evidence)[:300],
                answer_signal=ev.verdict,
                note=ev.discrepancy_note,
            )
        ]
    return out

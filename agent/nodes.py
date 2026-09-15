from agent.llm import chat_model, structured
from agent.state import InterviewState, JDAnalysis, ResumeAnalysis, TopicPlan, TopicRun, Event, Question, Evaluation, Discrepancy
from agent.utils import allocate_time, pace, question_time_limit, QUESTION_OVERHEAD_S 
from agent.conditions import baseline_difficulty, topic_difficulty, depth_credit, next_mode, adjust_difficulty


from datetime import datetime
from langgraph.types import interrupt


def _event(kind: str, state: InterviewState, **kwargs) -> Event:
    return Event(
        kind=kind,
        t_offset_s=round(state.get("elapsed_s", 0.0), 1),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        **kwargs,
    )


def analyze_jd(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    jd = structured(
        llm,
        JDAnalysis,
        system=(
            "Extract structured requirements from a job description. `seniority` "
            "must be one of: intern, junior, mid, senior, lead, staff, principal. "
            "`must_have` are hard requirements, `nice_to_have` are preferences. "
            "Do not invent requirements the text does not state."
        ),
        user=state["jd_text"],
    )
    return {"jd_analysis": jd}

def analyze_resume(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.1)
    resume = structured(
        llm,
        ResumeAnalysis,
        system=(
            "Extract what this resume claims: skills, tools, projects, roles, "
            "domains, total years of experience. Record claims verbatim in spirit; "
            "never infer a skill that is not written down. These are claims to be "
            "validated in interview, not established facts."
        ),
        user=state["resume_text"],
    )
    return {"resume_analysis": resume}


def plan_topics(state: InterviewState) -> dict:
    llm = chat_model(temperature=0.5)
    jd, resume = state["jd_analysis"], state["resume_analysis"]
    total_seconds = state["total_seconds"]
    suggested = max(3, min(8, total_seconds // 360))

    plan = structured(
        llm,
        TopicPlan,
        system=(
            f"Choose about {suggested} interview topics for a "
            f"{jd.seniority} {jd.role_title} screen, ordered as they should be "
            "asked: an accessible topic first, hardest topics in the middle, never "
            "a gap topic first. Rules for each topic: `priority` 5 for a must-have "
            "the role fails without, 1 for peripheral. `source` is jd_required, "
            "jd_preferred, resume_claim, gap, or domain. Mark `is_gap` when the JD "
            "requires it and the resume shows no evidence. Mark "
            "`claimed_on_resume` when the resume evidences it, and put the "
            "specific resume lines in `resume_evidence` so questions can cite "
            "them. `target_depth` 1-5 is how deep this topic needs to go for this "
            "seniority. Cover every must-have of priority 4 or 5; ids are short "
            "slugs like 'postgres-transactions'."
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

def route(state: InterviewState) -> str:
    return "generate_question" if state.get("next_action") == "ask" else "build_report"


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


def generate_question(state: InterviewState) -> dict:
    topic = next(t for t in state["topics"] if t.id == state["current_topic_id"])
    run = state["topic_runs"][topic.id]
    mode = state.get("next_mode", "opening")
    counter = state.get("question_counter", 0) + 1

    topic_remaining = max(30.0, topic.allocated_seconds - run.elapsed_s)
    expected_left = 2 if mode == "opening" else 1
    limit = question_time_limit(topic_remaining, expected_left)

    history = "\n".join(
        f"{e.kind.upper()}: {e.text}"
        for e in state.get("transcript", [])
        if e.topic_id == topic.id and e.kind in {"question", "answer"}
    )[-3000:]

    mode_brief = {
        "opening": (
            "Ask a NEW question on this topic. If the resume evidences it, anchor "
            "the question in that specific project or claim."
        ),
        "followup": (
            "Ask ONE probing follow-up to the last answer: push for the concrete "
            "detail, trade-off, or failure case it skipped. Do not repeat the "
            "original question."
        ),
        "clarification": (
            "The last answer missed the question. Politely restate what you are "
            "asking, more narrowly and concretely. Do not penalise or lecture."
        ),
    }[mode]

    llm = chat_model(temperature=0.6)
    question = structured(
        llm,
        Question,
        system=(
            "You are a working engineer conducting a live interview. Output one "
            f"question at difficulty {run.difficulty}/5 (1 = definitions, "
            "3 = practical application with trade-offs, 5 = ambiguous design or "
            f"deep internals). {mode_brief} Constraints: one question only, no "
            "multi-part questions, answerable out loud in the time limit, never "
            "answerable with yes or no, no preamble or pleasantries. "
            "`looking_for` is a short note on what a strong answer contains."
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
    spent = float(reply.get("elapsed_s", 0.0)) + QUESTION_OVERHEAD_S
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
        ev = structured(
            llm,
            Evaluation,
            system=(
                "Score one interview answer on five 1-5 dimensions: relevance, "
                "depth, specificity, correctness, communication. Calibrate to the "
                "question's difficulty - a level-2 answer to a level-5 question is "
                "not a 5. Generic answers with no concrete example score 2 or below "
                "on specificity. `verdict` is one sentence a hiring manager would "
                "read. Set `contradicts_resume` only when the answer is materially "
                "weaker or inconsistent with the resume claim shown, and explain in "
                "`discrepancy_note`. Set `needs_validation` when a later round "
                "should re-test this. Keep any quotation from the answer under ten "
                "words."
            ),
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

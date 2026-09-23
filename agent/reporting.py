from agent.state import InterviewState, ReportNarrative
from agent.llm import chat_model, structured, get_system_prompt
from agent.prompt import REPORT_NARRATIVE_SYSTEM
from agent.utils import coverage_ratio, wrap_up_reserve

from datetime import datetime
import json


SIGNAL_LABEL = {
    "strong": "Strong",
    "mixed": "Mixed",
    "weak": "Weak",
    "insufficient": "Insufficient signal",
}

RECOMMENDATION_LABEL = {
    "advance": "Advance",
    "borderline": "Borderline",
    "do_not_advance": "Do not advance",
}

DIMENSIONS = ("relevance", "depth", "specificity", "correctness", "communication")


def _mmss(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _completion_status(state: InterviewState, topics, runs, unassessed) -> str:
    """How the interview actually ended, independent of planning-time drops."""
    if not state.get("question_counter"):
        return "abandoned"
    total = state["total_seconds"]
    elapsed = state.get("elapsed_s", 0.0)
    if unassessed and elapsed >= total - wrap_up_reserve(total):
        return "time_expired"
    return "completed"


def _turns(state: InterviewState) -> list[dict]:
    """Question/answer/evaluation triples, in order, keyed by question id."""
    by_question: dict[str, dict] = {}
    for event in state.get("transcript", []):
        if not event.question_id:
            continue
        turn = by_question.setdefault(
            event.question_id,
            {"topic_id": event.topic_id, "question": "", "answer": "",
             "mode": "", "difficulty": None, "answer_s": None, "timed_out": False},
        )
        if event.kind == "question":
            turn["question"] = event.text
            turn["mode"] = event.meta.get("mode", "")
            turn["difficulty"] = event.meta.get("difficulty")
        elif event.kind == "answer":
            turn["answer"] = event.text
            turn["answer_s"] = event.meta.get("answer_s")
            turn["timed_out"] = bool(event.meta.get("timed_out"))
    for evaluation in state.get("evaluations", []):
        if evaluation.question_id in by_question:
            by_question[evaluation.question_id]["evaluation"] = evaluation
    return list(by_question.values())


def _evidence(state: InterviewState, topics, runs, turns, max_chars: int = 14000) -> str:
    """Every topic with its full question/answer trail, for the LLM to read."""
    blocks: list[str] = []
    for topic in topics:
        run = runs[topic.id]
        topic_turns = [t for t in turns if t["topic_id"] == topic.id]
        header = (
            f"TOPIC {topic.id}: {topic.name} (priority {topic.priority}, "
            f"{'resume claim' if topic.claimed_on_resume else 'gap' if topic.is_gap else topic.source}) "
            f"- {run.status}, depth {run.depth_reached}/{topic.target_depth}, "
            f"{run.questions_asked} question(s) in {_mmss(run.elapsed_s)} "
            f"of {_mmss(topic.allocated_seconds)}"
        )
        if not topic_turns:
            blocks.append(f"{header}\n  NOT ASSESSED - no questions asked.")
            continue

        lines = [header]
        for turn in topic_turns:
            evaluation = turn.get("evaluation")
            lines.append(
                f"  Q ({turn['mode']}, difficulty {turn['difficulty']}/5): {turn['question']}"
            )
            lines.append(
                f"  A ({turn['answer_s']}s"
                f"{', timer expired' if turn['timed_out'] else ''}): "
                f"{(turn['answer'] or '(no answer)')[:1200]}"
            )
            if evaluation:
                lines.append(
                    f"  SCORED {evaluation.overall}/5 "
                    + " ".join(f"{d[:4]} {getattr(evaluation, d)}" for d in DIMENSIONS)
                    + f" - {evaluation.verdict}"
                    + (f" | strength: {evaluation.strength_note}" if evaluation.strength_note else "")
                    + (f" | gap: {evaluation.gap_note}" if evaluation.gap_note else "")
                )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:max_chars]


def _narrative(state: InterviewState, topics, runs, turns, status, covered, at_depth):
    """The single report LLM call. Returns None when it fails."""
    jd, resume = state["jd_analysis"], state["resume_analysis"]
    total = state["total_seconds"]
    elapsed = state.get("elapsed_s", 0.0)
    discrepancies = state.get("discrepancies", [])

    context = (
        f"ROLE: {jd.seniority} {jd.role_title}\n"
        f"MUST HAVE: {', '.join(jd.must_have) or 'n/a'}\n"
        f"CANDIDATE: {resume.name}, {resume.years_experience:g} years claimed\n"
        f"INTERVIEW: {_mmss(elapsed)} of {_mmss(total)} used, "
        f"{state.get('question_counter', 0)} questions, ended as {status}\n"
        f"COVERAGE: {len(covered)}/{len(topics)} topics covered, "
        f"{len(at_depth)} reached target depth\n"
    )
    if state.get("dropped_topics"):
        context += (
            "DROPPED AT PLANNING TIME (never in scope): "
            f"{', '.join(state['dropped_topics'])}\n"
        )
    if discrepancies:
        context += "RESUME CONFLICTS FLAGGED DURING THE INTERVIEW:\n" + "\n".join(
            f"- [{d.topic_id}] {d.note} (claim: {d.resume_claim[:200]})"
            for d in discrepancies
        ) + "\n"

    try:
        return structured(
            chat_model(temperature=0.3),
            ReportNarrative,
            system=get_system_prompt("REPORT_NARRATIVE_SYSTEM", REPORT_NARRATIVE_SYSTEM),
            user=f"{context}\nEVIDENCE\n{_evidence(state, topics, runs, turns)}",
        )
    except ValueError:
        return None


def build_report(state: InterviewState) -> dict:
    topics = state["topics"]
    runs = state["topic_runs"]
    evaluations = state.get("evaluations", [])
    discrepancies = state.get("discrepancies", [])
    jd, resume = state["jd_analysis"], state["resume_analysis"]
    turns = _turns(state)

    covered = [t for t in topics if runs[t.id].status == "covered"]
    unassessed = [t for t in topics if not runs[t.id].questions_asked]
    at_depth = [t for t in covered if runs[t.id].depth_reached >= t.target_depth]
    status = _completion_status(state, topics, runs, unassessed)

    scored = [e.overall for e in evaluations]
    average = round(sum(scored) / len(scored), 2) if scored else 0.0
    dimension_means = {
        d: round(sum(getattr(e, d) for e in evaluations) / len(evaluations), 1)
        for d in DIMENSIONS
    } if evaluations else {}

    timed_out = sum(1 for t in turns if t["timed_out"])
    no_answer = sum(1 for t in turns if not (t["answer"] or "").strip())
    validate = [e for e in evaluations if e.needs_validation]

    narrative = (
        _narrative(state, topics, runs, turns, status, covered, at_depth)
        if evaluations else None
    )

    lines: list[str] = [
        f"# Interview report - {resume.name}",
        "",
        f"**{jd.role_title} ({jd.seniority})** - "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    if narrative:
        lines += [
            f"## Recommendation: {RECOMMENDATION_LABEL[narrative.recommendation]} "
            f"({narrative.confidence} confidence)",
            "",
            f"**{narrative.headline}**" if narrative.headline else "",
            "",
            narrative.recommendation_reasoning,
            "",
        ]
    else:
        lines += [
            "## Recommendation: not generated",
            "",
            "The report model did not return a usable judgement. The evidence "
            "below and the transcript still stand on their own.",
            "",
        ]

    lines += [
        "## At a glance",
        "",
        "| | |",
        "|---|---|",
        f"| Time used | {_mmss(state.get('elapsed_s', 0.0))} of {_mmss(state['total_seconds'])} |",
        f"| Completion | `{status}` |",
        f"| Topics covered | {len(covered)}/{len(topics)} "
        f"({coverage_ratio(len(covered), len(topics)):.0%}), {len(at_depth)} at target depth |",
        f"| Questions asked | {state.get('question_counter', 0)} |",
        f"| Average answer score | {average}/5 |",
    ]
    if timed_out or no_answer:
        lines.append(
            f"| Timing | {timed_out} answer(s) cut off by the timer, "
            f"{no_answer} left unanswered |"
        )
    if dimension_means:
        lines += [
            "",
            "| " + " | ".join(d.capitalize() for d in DIMENSIONS) + " |",
            "|" + "---|" * len(DIMENSIONS),
            "| " + " | ".join(f"{dimension_means[d]}/5" for d in DIMENSIONS) + " |",
        ]
    lines.append("")

    if narrative:
        if narrative.summary:
            lines += ["## How the candidate performed", "", narrative.summary, ""]

        lines += ["### Strengths", ""]
        lines += [
            f"- **{_topic_name(topics, p.topic_id)}** - {p.point}"
            for p in narrative.strengths
        ] or ["- None recorded."]

        lines += ["", "### Concerns", ""]
        lines += [
            f"- **{_topic_name(topics, p.topic_id)}** - {p.point}"
            for p in narrative.concerns
        ] or ["- None recorded."]

        if narrative.risk_note:
            lines += ["", "### Main risk", "", narrative.risk_note]
        lines.append("")

    lines += [
        "## Topic by topic",
        "",
        "| Topic | Priority | Signal | Used / budget | Qs | Depth | Mean | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    signals = {n.topic_id: n for n in (narrative.topic_notes if narrative else [])}
    for topic in topics:
        run = runs[topic.id]
        note = signals.get(topic.id)
        lines.append(
            f"| {topic.name} | {topic.priority} "
            f"| {SIGNAL_LABEL[note.signal] if note else '-'} "
            f"| {_mmss(run.elapsed_s)} / {_mmss(topic.allocated_seconds)} "
            f"| {run.questions_asked} | {run.depth_reached}/{topic.target_depth} "
            f"| {run.mean_score or '-'} | {run.status} |"
        )
    lines.append("")

    for topic in topics:
        note = signals.get(topic.id)
        if note and note.assessment:
            lines.append(f"- **{topic.name}** ({SIGNAL_LABEL[note.signal]}) - {note.assessment}")
    lines.append("")

    lines += ["## Resume-vs-answer discrepancies", ""]
    if discrepancies:
        for d in discrepancies:
            lines.append(f"- **{_topic_name(topics, d.topic_id)}** - {d.note or d.answer_signal}")
            if d.resume_claim:
                lines.append(f"  - Resume claim: {d.resume_claim}")
    else:
        lines.append("- None flagged.")

    lines += ["", "## Follow up in the next round", ""]
    if narrative and narrative.follow_ups:
        lines += [f"{i}. {q}" for i, q in enumerate(narrative.follow_ups, 1)]
    elif validate:
        lines += [
            f"- **{_topic_name(topics, e.topic_id)}** - {e.gap_note or e.verdict}"
            for e in validate
        ]
    else:
        lines.append("- Nothing flagged for re-testing.")

    if validate and narrative and narrative.follow_ups:
        lines += ["", "Answers the interviewer marked as needing validation:", ""]
        lines += [
            f"- **{_topic_name(topics, e.topic_id)}** - {e.gap_note or e.verdict}"
            for e in validate
        ]

    if unassessed:
        lines += ["", "## Not assessed", ""]
        lines += [
            f"- **{t.name}** (priority {t.priority}) - "
            f"{'planned but never reached' if runs[t.id].status in ('pending', 'skipped') else runs[t.id].status}"
            for t in unassessed
        ]
    if state.get("dropped_topics"):
        lines += [
            "",
            "Dropped at planning time because the budget could not cover them: "
            f"{', '.join(state['dropped_topics'])}.",
        ]

    lines += [
        "",
        "---",
        "",
        "_Scores are structured interview notes produced by a language model, "
        "not a calibrated assessment. Use them alongside a human read of the "
        "transcript, not instead of one._",
        "",
    ]
    return {"report": "\n".join(lines), "completion_status": status}


def _topic_name(topics, topic_id: str) -> str:
    return next((t.name for t in topics if t.id == topic_id), topic_id or "general")


def transcript_markdown(state: InterviewState) -> str:
    resume = state.get("resume_analysis")
    name = resume.name if resume else "Candidate"
    out = [f"# Interview transcript - {name}", ""]
    topics = {t.id: t for t in state.get("topics", [])}

    for event in state.get("transcript", []):
        stamp = _mmss(event.t_offset_s)
        if event.kind == "interview_start":
            out += [f"**[{stamp}] Interview start** - {event.text}", ""]
        elif event.kind == "topic_start":
            out += [
                f"## [{stamp}] Topic: {event.text}",
                "",
                f"_priority {event.meta.get('priority')}, "
                f"budget {_mmss(event.meta.get('allocated_s', 0))}, "
                f"target depth {event.meta.get('target_depth')}, "
                f"opening difficulty {event.meta.get('difficulty')}_",
                "",
            ]
        elif event.kind == "question":
            out += [
                f"**[{stamp}] Interviewer** "
                f"({event.meta.get('mode')}, difficulty "
                f"{event.meta.get('difficulty')}/5, "
                f"{event.meta.get('time_limit_s')}s): {event.text}",
                "",
            ]
        elif event.kind == "answer":
            flag = " _(timed out)_" if event.meta.get("timed_out") else ""
            out += [
                f"**[{stamp}] Candidate** "
                f"({event.meta.get('answer_s')}s){flag}: "
                f"{event.text or '_no answer_'}",
                "",
            ]
        elif event.kind == "evaluation":
            out += [
                f"> _Evaluation: {event.meta.get('overall')}/5 - {event.text}_",
                "",
            ]
        elif event.kind == "difficulty_change":
            out += [f"> _{event.text}_", ""]
        elif event.kind == "time_adjustment":
            out += [f"> _[{stamp}] Time adjustment: {event.text}_", ""]
        elif event.kind == "topic_end":
            topic = topics.get(event.topic_id)
            out += [
                f"_[{stamp}] End of topic{': ' + topic.name if topic else ''} - "
                f"{event.text}_",
                "",
            ]
        elif event.kind == "interview_end":
            out += [f"**[{stamp}] Interview end** - {event.text}", ""]
    return "\n".join(out)


def transcript_json(state: InterviewState) -> str:
    return json.dumps(
        {
            "role": state["jd_analysis"].model_dump(),
            "candidate": state["resume_analysis"].model_dump(),
            "total_seconds": state["total_seconds"],
            "elapsed_s": round(state.get("elapsed_s", 0.0), 1),
            "completion_status": state.get("completion_status"),
            "topics": [t.model_dump() for t in state.get("topics", [])],
            "topic_runs": {
                tid: {**run.model_dump(), "mean_score": run.mean_score}
                for tid, run in state.get("topic_runs", {}).items()
            },
            "dropped_topics": state.get("dropped_topics", []),
            "events": [e.model_dump() for e in state.get("transcript", [])],
            "evaluations": [
                {**e.model_dump(), "overall": e.overall}
                for e in state.get("evaluations", [])
            ],
            "discrepancies": [d.model_dump() for d in state.get("discrepancies", [])],
        },
        indent=2,
    )
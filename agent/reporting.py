
from agent.state import InterviewState
from agent.llm import chat_model
from agent.prompts import REPORT_NARRATIVE_SYSTEM
from agent.utils import coverage_ratio


from datetime import datetime
import json 

def _mmss(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def build_report(state: InterviewState) -> dict:
    topics = state["topics"]
    runs = state["topic_runs"]
    evaluations = state.get("evaluations", [])
    jd, resume = state["jd_analysis"], state["resume_analysis"]

    covered = [t for t in topics if runs[t.id].status == "covered"]
    skipped = [t for t in topics if runs[t.id].status in {"pending", "skipped"}]
    at_depth = [t for t in covered if runs[t.id].depth_reached >= t.target_depth]

    if skipped or state.get("dropped_topics"):
        status = "time_expired"
    else:
        status = "completed"

    scored = [e.overall for e in evaluations]
    average = round(sum(scored) / len(scored), 2) if scored else 0.0

    strengths = [e for e in evaluations if e.overall >= 4.0 and e.strength_note]
    gaps = [e for e in evaluations if e.overall <= 2.5 and e.gap_note]
    validate = [e for e in evaluations if e.needs_validation]
    discrepancies = state.get("discrepancies", [])

    evidence = "\n".join(
        f"[{e.topic_id}] score {e.overall}/5 - {e.verdict}"
        f"{' | strength: ' + e.strength_note if e.strength_note else ''}"
        f"{' | gap: ' + e.gap_note if e.gap_note else ''}"
        for e in evaluations
    )[:8000]

    llm = chat_model(temperature=0.3)
    narrative = llm.invoke(
        REPORT_NARRATIVE_SYSTEM
        + f"Role: {jd.seniority} {jd.role_title}\n"
        f"Candidate: {resume.name} ({resume.years_experience:g} yrs claimed)\n"
        f"Coverage: {len(covered)}/{len(topics)} topics, "
        f"{len(at_depth)} reached target depth\n"
        f"Interview ended: {status}\n\n"
        f"EVALUATIONS:\n{evidence}"
    ).content

    lines: list[str] = [
        f"# Interview summary - {resume.name}",
        "",
        f"- **Role:** {jd.role_title} ({jd.seniority})",
        f"- **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **Time budget:** {_mmss(state['total_seconds'])} "
        f"| **used:** {_mmss(state.get('elapsed_s', 0.0))}",
        f"- **Completion status:** `{status}`",
        f"- **Topic coverage:** {len(covered)}/{len(topics)} "
        f"({coverage_ratio(len(covered), len(topics)):.0%}), "
        f"{len(at_depth)} at target depth",
        f"- **Questions asked:** {state.get('question_counter', 0)}",
        f"- **Average answer score:** {average}/5",
        "",
        str(narrative),
        "",
        "### Topic coverage and depth",
        "",
        "| Topic | Priority | Allocated | Used | Qs | Depth | Target | Mean | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for topic in topics:
        run = runs[topic.id]
        lines.append(
            f"| {topic.name} | {topic.priority} | {_mmss(topic.allocated_seconds)} "
            f"| {_mmss(run.elapsed_s)} | {run.questions_asked} "
            f"| {run.depth_reached} | {topic.target_depth} "
            f"| {run.mean_score or '-'} | {run.status} |"
        )

    if state.get("dropped_topics"):
        lines += [
            "",
            "Topics dropped at planning time because the budget could not cover "
            f"them: {', '.join(state['dropped_topics'])}.",
        ]

    lines += ["", "### Resume-vs-answer discrepancies", ""]
    if discrepancies:
        for d in discrepancies:
            lines.append(f"- **{d.topic_id}** - {d.note}")
            if d.resume_claim:
                lines.append(f"  - Resume claim: {d.resume_claim}")
    else:
        lines.append("- None flagged.")

    lines += ["", "### Areas requiring further validation", ""]
    if validate:
        for e in validate:
            lines.append(f"- **{e.topic_id}** - {e.gap_note or e.verdict}")
    else:
        lines.append("- None flagged.")

    if skipped:
        lines += [
            "",
            "### Not assessed",
            "",
            *[
                f"- **{t.name}** (priority {t.priority}) - "
                f"{'ran out of time' if t.id in runs else 'not reached'}"
                for t in skipped
            ],
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

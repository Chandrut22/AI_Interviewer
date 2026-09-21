import os
import uuid
from pathlib import Path
from typing import Optional
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

import typer
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, IntPrompt

from agent.graph import build_graph
from agent.loader import load_text
from agent.reporting import transcript_json, transcript_markdown
from agent.timer import ask_timed
import sys
from dotenv import load_dotenv

load_dotenv()

from agent.langfuse import langfuse_handler

app = typer.Typer(
    add_completion=False, help="AI interviewer: topic-driven, time-boxed screens."
)
console = Console()

MODE_LABEL = {
    "opening": "new question",
    "followup": "follow-up",
    "clarification": "clarification",
}


def _render_question(payload: dict) -> None:
    left = max(0, payload["total_seconds"] - payload["elapsed_s"])
    console.print()

    # Render Clarification if present
    if payload.get("clarification"):
        console.print(
            Panel(
                payload["clarification"],
                title="Clarification",
                border_style="yellow",
            )
        )
        console.print()

    console.print(
        Panel(
            payload["text"],
            title=(
                f"Topic {payload['topic_index']}/{payload['topic_total']}: "
                f"{payload['topic']}  |  "
                f"{MODE_LABEL.get(payload['mode'], payload['mode'])}  |  "
                f"difficulty {payload['difficulty']}/5"
            ),
            subtitle=(
                f"answer in {payload['time_limit_s']}s  ·  "
                f"{left // 60}m {left % 60}s left in the interview  ·  "
                f"Qs left: {payload.get('questions_remaining', 'N/A')}  ·  "
                f"Doubts left: {payload.get('doubts_remaining', 'N/A')}"
            ),
            border_style="cyan" if payload["mode"] == "opening" else "magenta",
        )
    )


def _render_plan_table(result: dict) -> None:
    plan_table = Table(title="Interview plan", header_style="bold")
    for column in ("Topic", "Priority", "Budget", "Target depth", "Source"):
        plan_table.add_column(column, overflow="fold")
    for topic in result.get("topics", []):
        plan_table.add_row(
            topic.name,
            str(topic.priority),
            f"{topic.allocated_seconds // 60}:"
            f"{topic.allocated_seconds % 60:02d}",
            str(topic.target_depth),
            topic.source + (" (gap)" if topic.is_gap else ""),
        )
    console.print(plan_table)
    if result.get("dropped_topics"):
        console.print(
            "[yellow]Dropped for time:[/yellow] "
            f"{', '.join(result['dropped_topics'])} "
            "(raise --minutes to include them)"
        )


def _render_time_allocation_approval(payload: dict) -> None:
    total = payload["total_seconds"]
    table = Table(title="Proposed time allocation (LLM)", header_style="bold")
    for column in ("Topic", "Priority", "Seconds", "M:S"):
        table.add_column(column, overflow="fold")
    for t in payload["topics"]:
        secs = t["allocated_seconds"]
        table.add_row(t["name"], str(t["priority"]), str(secs), f"{secs // 60}:{secs % 60:02d}")
    console.print(table)
    if payload.get("dropped_for_time"):
        console.print(
            f"[yellow]Dropped for time by the planner:[/yellow] "
            f"{', '.join(payload['dropped_for_time'])}"
        )
    console.print(f"Total budget: {total // 60}m {total % 60}s")


def _render_time_allocation_input(payload: dict) -> None:
    console.print(
        f"\n[cyan]{payload['topic_name']}[/cyan] (priority {payload['priority']}) - "
        f"suggested {payload['suggested_seconds']}s "
        f"(total budget {payload['total_seconds']}s, "
        f"{payload['allocated_so_far']}s assigned so far)"
    )


def _loop(graph, config, result: dict) -> dict:
    plan_shown = False

    def _maybe_show_plan(res: dict) -> None:
        nonlocal plan_shown
        if not plan_shown and res.get("topics"):
            _render_plan_table(res)
            plan_shown = True

    while True:
        pending = result.get("__interrupt__")
        if not pending:
            return result
        payload = pending[0].value
        itype = payload.get("type", "question")

        if itype == "time_allocation_approval":
            _render_time_allocation_approval(payload)
            approved = Confirm.ask("Approve this time allocation?", default=True)
            result = graph.invoke(Command(resume={"approved": approved}), config=config)

        elif itype == "time_allocation_input":
            _render_time_allocation_input(payload)
            seconds = IntPrompt.ask(
                "Seconds for this topic", default=payload["suggested_seconds"]
            )
            result = graph.invoke(Command(resume={"seconds": seconds}), config=config)

        else:
            _render_question(payload)
            answer = ask_timed("answer >", payload["time_limit_s"])
            if answer.timed_out:
                console.print("[yellow]Time is up - submitting what you had.[/yellow]")
            console.print("[dim]evaluating...[/dim]")
            result = graph.invoke(
                Command(
                    resume={
                        "answer": answer.text,
                        "elapsed_s": answer.elapsed_s,
                        "timed_out": answer.timed_out,
                    }
                ),
                config=config,
            )

        _maybe_show_plan(result)


def _finish(result: dict, out: Path, thread_id: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.get("report", ""), encoding="utf-8")

    transcript_md = out.with_name(f"{out.stem}.transcript.md")
    transcript_md.write_text(transcript_markdown(result), encoding="utf-8")
    data = out.with_name(f"{out.stem}.transcript.json")
    data.write_text(transcript_json(result), encoding="utf-8")

    table = Table(title="Topic coverage", header_style="bold")
    for column in ("Topic", "Used / budget", "Qs", "Depth", "Mean", "Status"):
        table.add_column(column, overflow="fold")
    for topic in result.get("topics", []):
        run = result["topic_runs"][topic.id]
        table.add_row(
            topic.name,
            f"{int(run.elapsed_s // 60)}:{int(run.elapsed_s % 60):02d} / "
            f"{topic.allocated_seconds // 60}:{topic.allocated_seconds % 60:02d}",
            str(run.questions_asked),
            f"{run.depth_reached}/{topic.target_depth}",
            f"{run.mean_score or '-'}",
            run.status,
        )
    console.print()
    console.print(table)
    console.print(f"Status: [bold]{result.get('completion_status')}[/bold]")
    console.print(
        f"\nSummary: [green]{out}[/green]"
        f"\nTranscript: [green]{transcript_md}[/green]"
        f"\nStructured: [green]{data}[/green]"
        f"\nThread id: [cyan]{thread_id}[/cyan] (pass to `resume-interview`)"
    )


@app.command()
def run(
    resume: Path = typer.Option(..., "--resume", "-r", help="Resume: pdf, docx, txt"),
    jd: Path = typer.Option(..., "--jd", "-j", help="Job description file"),
    minutes: int = typer.Option(30, "--minutes", "-m", min=5, max=180,
                                help="Total interview time budget"),
    model: Optional[str] = typer.Option(None, "--model", help="OpenRouter model id"),
    # db: Path = typer.Option(Path("interviews.sqlite"), "--db"),
    out: Path = typer.Option(Path("output/report.md"), "--out", "-o"),
    thread: Optional[str] = typer.Option(None, "--thread"),
) -> None:
    """Run a fresh interview."""



    db = os.getenv("POSTGRES_CONNSTR")
    if not db:
        console.print("[red]Error:[/red] POSTGRES_CONNSTR environment variable is not set. Specify a valid PostgreSQL URI before running 'python main.py'.")
        sys.exit(1)


    resume_text = load_text(resume)
    jd_text = load_text(jd)
    thread_id = thread or f"iv-{uuid.uuid4().hex[:8]}"

    with PostgresSaver.from_conn_string(db) as checkpointer:
        try:
            checkpointer.setup()
        except Exception as e:
            console.print(f"[red]Error creating tables in Postgres: {e}")
            sys.exit(1)

        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id},"callbacks":[langfuse_handler],"metadata": { "langfuse_session_id": thread_id,"langfuse_tags": ["ai-interviewer"]}}
        console.print("[dim]analysing job description and resume...[/dim]")
        result = graph.invoke(
            {
                "resume_text": resume_text,
                "jd_text": jd_text,
                "total_seconds": minutes * 60,
                "transcript": [],
                "evaluations": [],
                "discrepancies": [],
            },
            config=config,
        )

        result = _loop(graph, config, result)
        _finish(result, out, thread_id)


if __name__ == "__main__":
    app()

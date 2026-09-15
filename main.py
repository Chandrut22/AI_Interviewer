
import os
import uuid
from pathlib import Path
from typing import Optional

import typer
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent.graph import build_graph
from agent.loaders import load_text
from agent.reporting import transcript_json, transcript_markdown
from agent.timer import ask_timed
import sys
from dotenv import load_dotenv

load_dotenv()

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
                f"{left // 60}m {left % 60}s left in the interview"
            ),
            border_style="cyan" if payload["mode"] == "opening" else "magenta",
        )
    )


def _loop(graph, config, result: dict) -> dict:
    while True:
        pending = result.get("__interrupt__")
        if not pending:
            return result
        payload = pending[0].value
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
    if model:
        os.environ["OPENROUTER_MODEL"] = model



    db = os.getenv("POSTGRES_CONNSTR")
    print(db)
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
        config = {"configurable": {"thread_id": thread_id}}
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

        result = _loop(graph, config, result)
        _finish(result, out, thread_id)


if __name__ == "__main__":
    app()

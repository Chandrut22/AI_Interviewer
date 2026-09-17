# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup & Installation
- Install dependencies: `uv sync`

### Running the Application
- Start a new interview: `python main.py run --resume <resume_path> --jd <jd_path> --minutes <duration>`
- Resume an existing interview: `python main.py run --thread <thread_id>`

### Common CLI Options
- `--resume, -r`: Path to candidate's resume (PDF, DOCX, TXT)
- `--jd, -j`: Path to job description (TXT)
- `--minutes, -m`: Total interview budget (default: 30)
- `--model`: OpenRouter model ID override
- `--out, -o`: Final report output path (default: `output/report.md`)

## Architecture & Structure

### High-Level Overview
The AI Interviewer is a topic-driven, time-boxed screening system built as a Finite State Machine using **LangGraph**. It implements the **Saga Pattern** to allow interviews to be interrupted and resumed via PostgreSQL checkpointing.

### Core Module: `agent/`
The `agent/` directory contains the core intelligence engine:
- `graph.py`: Defines the LangGraph state machine, nodes, and transitions.
- `state.py`: Manages `InterviewState` (a `TypedDict` persisted across nodes) and Pydantic models for topics and evaluations.
- `node.py`: Implements the business logic for each graph step (Analysis, Planning, Questioning, Evaluation).
- `llm.py`: A structured LLM wrapper that enforces Pydantic schemas via a validation-feedback loop.
- `utils.py`: The "Math Engine" that calculates time budgets and pacing to ensure topic coverage within the global time limit.
- `reporting.py`: Synthesizes the collected evaluations and transcript into a final Markdown/JSON report.
- `loader.py`: Handles document extraction from PDF, DOCX, and TXT.
- `prompt.py`: Centralized repository for LLM system prompts.

### Interview Workflow
1. **Analysis**: Simultaneously analyzes the JD and Resume to identify core competencies.
2. **Planning**: Generates a syllabus with priority-weighted time budgets for each topic.
3. **Execution Loop**:
   - `decide_next`: Selects the next critical topic based on remaining time and priority.
   - `generate_question`: Creates a targeted question using the LLM.
   - `ask_question`: Pauses execution (LangGraph interrupt) to capture timed user input via the CLI.
   - `evaluate_answer`: Scores the response and updates the state's depth/difficulty.
4. **Reporting**: Produces a final comprehensive evaluation of the candidate.

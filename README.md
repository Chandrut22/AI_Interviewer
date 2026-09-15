# AI Interviewer

AI Interviewer is a sophisticated, topic-driven, and time-boxed automated screening system. It leverages Large Language Models (LLMs) and LangGraph to conduct structured technical interviews by analyzing a candidate's resume against a specific job description.

## 🚀 Features

- **Dynamic Interview Planning**: Automatically analyzes the Job Description (JD) and candidate's Resume to identify key topics, priorities, and potential gaps.
- **Adaptive Questioning**: Generates a mix of opening questions, deep-dive follow-ups, and clarifications based on the candidate's real-time responses.
- **Strict Time Boxing**: Manages a total interview budget and allocates specific time windows to each topic, ensuring comprehensive coverage within the time limit.
- **Persistence & Resumability**: Uses PostgreSQL for state checkpointing, allowing interviews to be paused and resumed using a `thread_id`.
- **Comprehensive Analytics**: Produces a detailed final evaluation report, as well as structured (JSON) and human-readable (Markdown) transcripts.
- **Professional CLI**: Built with `typer` and `rich` for a high-quality terminal-based interview experience.

## 🛠️ Tech Stack

- **Language**: Python 3.11+
- **Orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph)
- **CLI Framework**: [Typer](https://typer.tiangolo.com/)
- **Terminal UI**: [Rich](https://rich.readthedocs.io/)
- **Database**: PostgreSQL (via `langgraph.checkpoint.postgres`)
- **LLM Gateway**: OpenRouter (configurable models)

## 📋 Prerequisites

- Python 3.11 or higher
- A running PostgreSQL instance
- An OpenRouter API key

## ⚙️ Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/ai-interviewer.git
   cd ai-interviewer
   ```

2. **Install dependencies**:
   It is recommended to use `uv` for fast installation:
   ```bash
   pip install uv
   uv sync
   ```

3. **Environment Setup**:
   Create a `.env` file in the root directory:
   ```env
   OPENROUTER_API_KEY=your_api_key_here
   POSTGRES_CONNSTR=postgresql://user:password@localhost:5432/dbname
   ```

## 🚀 Usage

Run a new interview by providing the resume and job description files:

```bash
python main.py run --resume CV_Developer.pdf --jd jd.txt --minutes 30
```

### Command-line Options:
- `--resume, -r`: Path to the candidate's resume (PDF, DOCX, TXT).
- `--jd, -j`: Path to the job description file (TXT).
- `--minutes, -m`: Total interview time budget (default: 30).
- `--model`: Specify a custom OpenRouter model ID.
- `--out, -o`: Path to save the final report (default: `output/report.md`).
- `--thread`: Provide an existing `thread_id` to resume a previous interview.

## 📐 Workflow

The system follows a deterministic graph-based workflow:
1. **Analysis**: Scans JD and Resume $\rightarrow$ Identifies core competencies.
2. **Planning**: Allocates time budgets and target depths for each topic.
3. **Execution Loop**:
   - `Decide Next` $\rightarrow$ Selects the most critical topic.
   - `Generate Question` $\rightarrow$ Creates a targeted question.
   - `Ask Question` $\rightarrow$ Interacts with the candidate (with a timer).
   - `Evaluate Answer` $\rightarrow$ Scores the response and determines if follow-ups are needed.
4. **Reporting**: Synthesizes all evaluations into a final candidate report.

## 📁 Output

The system generates three files in the `output/` directory:
- `report.md`: A comprehensive evaluation of the candidate's fit.
- `report.transcript.md`: A human-readable log of the conversation.
- `report.transcript.json`: A structured data file containing all questions, answers, and scores.

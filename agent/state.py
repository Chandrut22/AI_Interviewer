import operator
from typing import Annotated, Literal, Optional, TypedDict
from pydantic import BaseModel, Field

TopicSource = Literal["jd_required", "jd_preferred", "resume_claim", "gap", "domain"]
EventKind = Literal["interview_start", "topic_start", "question", "answer", "evaluation", "difficulty_change", "time_adjustment", "violation", "topic_end", "interview_end"]
Mode = Literal["opening", "followup", "clarification"]
Completion = Literal["completed", "time_expired", "terminated", "abandoned", "in_progress"]

class JDAnalysis(BaseModel):
    role_title: str = "the role"
    seniority: str = "mid"
    years_required: float = 0.0
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    domain: str = ""
    responsibilities: list[str] = Field(default_factory=list)


class ResumeAnalysis(BaseModel):
    name: str = "Candidate"
    years_experience: float = 0.0
    skills_claimed: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)

class Topic(BaseModel):
    id: str
    name: str
    priority: int = Field(default=3, ge=1, le=5)
    source: TopicSource = "jd_required"
    rationale: str = ""
    target_depth: int = Field(default=3, ge=1, le=5)
    resume_evidence: list[str] = Field(default_factory=list)
    claimed_on_resume: bool = False
    is_gap: bool = False
    allocated_seconds: int = 0
    planned_questions: int = Field(default=0, ge=0, le=8)
    seconds_per_question: int = Field(default=0, ge=0, le=300)
    calculation: str = ""
    time_rationale: str = ""


class DroppedTopic(BaseModel):
    id: str
    name: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    reason: str = ""


class TopicPlan(BaseModel):
    allocatable_seconds: int = 0
    topics: list[Topic] = Field(default_factory=list)
    dropped: list[DroppedTopic] = Field(default_factory=list)
    total_allocated_seconds: int = 0

class TopicRun(BaseModel):
    """Mutable per-topic progress."""

    status: Literal["pending", "active", "covered", "skipped"] = "pending"
    elapsed_s: float = 0.0
    questions_asked: int = 0
    followups_used: int = 0
    clarifications_used: int = 0
    depth_reached: int = 0
    difficulty: int = 3
    scores: list[float] = Field(default_factory=list)
    consecutive_low_depth_answers: int = 0
    extended_s: int = 0  # extra seconds the orchestrator borrowed for this topic

    @property
    def mean_score(self) -> float:
        return round(sum(self.scores) / len(self.scores), 2) if self.scores else 0.0

class Event(BaseModel):
    """One transcript entry. `t_offset_s` is interview time, not wall clock."""

    kind: EventKind
    t_offset_s: float = 0.0
    timestamp: str = ""
    topic_id: str = ""
    question_id: str = ""
    text: str = ""
    meta: dict = Field(default_factory=dict)

class Question(BaseModel):
    id: str = ""
    topic_id: str = ""
    text: str = ""
    clarification: Optional[str] = None
    mode: Mode = "opening"
    difficulty: int = Field(default=3, ge=1, le=5)
    time_limit_s: int = 120
    looking_for: str = ""

class Evaluation(BaseModel):
    question_id: str = ""
    topic_id: str = ""
    relevance: int = Field(default=3, ge=1, le=5)
    depth: int = Field(default=3, ge=1, le=5)
    specificity: int = Field(default=3, ge=1, le=5)
    correctness: int = Field(default=3, ge=1, le=5)
    communication: int = Field(default=3, ge=1, le=5)
    verdict: str = ""
    strength_note: str = ""
    gap_note: str = ""
    contradicts_resume: bool = False
    discrepancy_note: str = ""
    needs_validation: bool = False

    @property
    def overall(self) -> float:
        parts = [
            self.relevance,
            self.depth,
            self.specificity,
            self.correctness,
            self.communication,
        ]
        return round(sum(parts) / len(parts), 2)


class Violation(BaseModel):
    """A candidate reply that broke the interview's rules of engagement."""

    topic_id: str = ""
    question_id: str = ""
    reason: str = ""          # e.g. "prompt extraction", "abusive language"
    detected_by: Literal["pattern", "model"] = "model"
    text: str = ""            # what the candidate sent, trimmed
    count: int = 0            # the running warning number


class Discrepancy(BaseModel):
    topic_id: str = ""
    resume_claim: str = ""
    answer_signal: str = ""
    note: str = ""

OrchestratorAction = Literal["continue_topic", "next_topic", "skip_topic", "wrap_up"]


class OrchestratorDecision(BaseModel):
    """Everything decide_next needs from its single LLM call per candidate turn."""

    # 1. Classify the reply.
    response_type: Literal["answer", "doubt", "skip_topic", "violation"]
    classification_reasoning: str = ""
    # Why the reply was a violation - for the record only, never shown to the candidate.
    violation_reason: str = ""
    # 2. Evaluate it (only meaningful when response_type == "answer").
    relevance: int = Field(default=3, ge=1, le=5)
    depth: int = Field(default=3, ge=1, le=5)
    specificity: int = Field(default=3, ge=1, le=5)
    correctness: int = Field(default=3, ge=1, le=5)
    communication: int = Field(default=3, ge=1, le=5)
    verdict: str = ""
    strength_note: str = ""
    gap_note: str = ""
    contradicts_resume: bool = False
    discrepancy_note: str = ""
    needs_validation: bool = False
    # 3. What to do next.
    action: OrchestratorAction = "continue_topic"
    action_reasoning: str = ""
    # 4. Shape of the next question (used by generate_question).
    next_difficulty: int = Field(default=3, ge=1, le=5)
    difficulty_reasoning: str = ""
    next_mode: Mode = "opening"
    next_question_focus: str = ""
    # Reply sent back to the candidate when they ask a doubt.
    doubt_reply: str = ""
    # 5. Dynamic time: extra seconds for the current topic, taken from the last topics.
    extend_topic_seconds: int = Field(default=0, ge=0, le=300)
    extension_reasoning: str = ""

    def to_evaluation(self) -> "Evaluation":
        return Evaluation(**self.model_dump(include={
            "relevance", "depth", "specificity", "correctness", "communication",
            "verdict", "strength_note", "gap_note", "contradicts_resume",
            "discrepancy_note", "needs_validation",
        }))

Signal = Literal["strong", "mixed", "weak", "insufficient"]


class ReportPoint(BaseModel):
    topic_id: str = ""
    point: str


class TopicNote(BaseModel):
    topic_id: str
    signal: Signal = "insufficient"
    assessment: str = ""


class ReportNarrative(BaseModel):
    """The judgement half of the report, written by the LLM from the evidence."""

    recommendation: Literal["advance", "borderline", "do_not_advance"]
    confidence: Literal["low", "medium", "high"] = "medium"
    headline: str = ""
    recommendation_reasoning: str = ""
    summary: str = ""
    strengths: list[ReportPoint] = Field(default_factory=list)
    concerns: list[ReportPoint] = Field(default_factory=list)
    topic_notes: list[TopicNote] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    risk_note: str = ""


class InterviewState(TypedDict, total=False):
    # inputs
    resume_text: str
    jd_text: str
    total_seconds: int
    # analysis
    jd_analysis: JDAnalysis
    resume_analysis: ResumeAnalysis
    topics: list[Topic]
    dropped_topics: list[str]
    # live control
    topic_runs: dict[str, TopicRun]
    topic_order: list[str]
    current_topic_id: Optional[str]
    pending_question: Optional[Question]
    next_mode: Mode
    next_action: Literal["ask", "wrap_up"]
    last_response_type: Literal["answer", "doubt", "skip_topic", "violation", None]
    question_focus: str
    clarification_reply: str  # orchestrator's answer to a candidate doubt
    warning_text: str         # conduct warning shown before the question is re-asked
    violation_count: int
    pacing_note: str
    elapsed_s: float
    question_counter: int
    doubt_count: int
    # records
    transcript: Annotated[list[Event], operator.add]
    evaluations: Annotated[list[Evaluation], operator.add]
    discrepancies: Annotated[list[Discrepancy], operator.add]
    violations: Annotated[list[Violation], operator.add]
    # outputs
    completion_status: Completion
    report: str




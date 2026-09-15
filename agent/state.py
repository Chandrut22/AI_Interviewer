

import operator
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

TopicSource = Literal["jd_required", "jd_preferred", "resume_claim", "gap", "domain"]
Mode = Literal["opening", "followup", "clarification"]
EventKind = Literal[
    "interview_start",
    "topic_start",
    "question",
    "answer",
    "evaluation",
    "difficulty_change",
    "topic_end",
    "interview_end",
]
Completion = Literal["completed", "time_expired", "abandoned", "in_progress"]


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

    @property
    def mean_score(self) -> float:
        return round(sum(self.scores) / len(self.scores), 2) if self.scores else 0.0


class TopicPlan(BaseModel):
    topics: list[Topic] = Field(default_factory=list)


class Question(BaseModel):
    id: str = ""
    topic_id: str = ""
    text: str = ""
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


class Discrepancy(BaseModel):
    topic_id: str = ""
    resume_claim: str = ""
    answer_signal: str = ""
    note: str = ""


class Event(BaseModel):
    """One transcript entry. `t_offset_s` is interview time, not wall clock."""

    kind: EventKind
    t_offset_s: float = 0.0
    timestamp: str = ""
    topic_id: str = ""
    question_id: str = ""
    text: str = ""
    meta: dict = Field(default_factory=dict)


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
    pacing_note: str
    elapsed_s: float
    question_counter: int
    # records
    transcript: Annotated[list[Event], operator.add]
    evaluations: Annotated[list[Evaluation], operator.add]
    discrepancies: Annotated[list[Discrepancy], operator.add]
    # outputs
    completion_status: Completion
    report: str

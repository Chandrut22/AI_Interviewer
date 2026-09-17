from langgraph.graph import START, END, StateGraph

from prev.nodes import (
    analyze_jd,
    analyze_resume,
    ask_question,
    decide_next,
    evaluate_answer,
    generate_question,
    plan_topics,
    route,
)
from prev.reporting import build_report
from prev.state import InterviewState


def build_graph(checkpointer):
    builder = StateGraph(InterviewState)
    builder.add_node("analyze_jd", analyze_jd)
    builder.add_node("analyze_resume", analyze_resume)
    builder.add_node("plan_topics", plan_topics)
    builder.add_node("decide_next", decide_next)
    builder.add_node("generate_question", generate_question)
    builder.add_node("ask_question", ask_question)
    builder.add_node("evaluate_answer", evaluate_answer)
    builder.add_node("build_report", build_report)

    builder.add_edge(START, "analyze_jd")
    builder.add_edge("analyze_jd", "analyze_resume")
    builder.add_edge("analyze_resume", "plan_topics")
    builder.add_edge("plan_topics", "decide_next")
    builder.add_conditional_edges(
        "decide_next",
        route,
        {"generate_question": "generate_question", "build_report": "build_report"},
    )
    builder.add_edge("generate_question", "ask_question")
    builder.add_edge("ask_question", "evaluate_answer")
    builder.add_edge("evaluate_answer", "decide_next")
    builder.add_edge("build_report", END)

    # graph = builder.compile(checkpointer=checkpointer)

    # png_data = graph.get_graph().draw_mermaid_png()
    # with open("langgraph_workflow.png", "wb") as f:
    #     f.write(png_data)

    return builder.compile(checkpointer=checkpointer)
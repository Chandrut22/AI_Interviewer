from langgraph.graph import END, START, StateGraph

from agent.node import analyze_jd, analyze_resume, plan_topics, approve_time_allocation, decide_next,generate_question, ask_question, route
from agent.reporting import build_report
from agent.state import InterviewState


def build_graph(checkpointer=None):
    builder = StateGraph(InterviewState)
    builder.add_node("analyze_jd", analyze_jd)
    builder.add_node("analyze_resume", analyze_resume)
    builder.add_node("plan_topics", plan_topics)
    builder.add_node("approve_time_allocation", approve_time_allocation)
    builder.add_node("decide_next", decide_next)
    builder.add_node("generate_question", generate_question)
    builder.add_node("ask_question", ask_question)
    builder.add_node("build_report", build_report)

    builder.add_edge(START, "analyze_jd")
    builder.add_edge(START, "analyze_resume")
    builder.add_edge(["analyze_resume","analyze_jd"], "plan_topics")
    builder.add_edge("plan_topics", "approve_time_allocation")
    builder.add_edge("approve_time_allocation", "decide_next")
    builder.add_conditional_edges(
        "decide_next",
        route,
        {"generate_question": "generate_question", "build_report": "build_report"},
    )
    builder.add_edge("generate_question", "ask_question")
    builder.add_edge("ask_question", "decide_next")
    builder.add_edge("build_report", END)

    graph = builder.compile(checkpointer=checkpointer)

    png_data = graph.get_graph().draw_mermaid_png()
    with open("langgraph_workflow.png", "wb") as f:
        f.write(png_data)

    return builder.compile(checkpointer=checkpointer)

graph = build_graph()
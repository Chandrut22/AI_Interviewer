import os
import uuid
from v2.graph import build_graph
from v2.loader import load_text
from langgraph.checkpoint.postgres import PostgresSaver
from langfuse import get_client
from langfuse.langchain import CallbackHandler
import json

langfuse = get_client()
langfuse_handler = CallbackHandler()

def make_json_serializable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: make_json_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [make_json_serializable(v) for v in value]
    return value

db = os.getenv("POSTGRES_CONNSTR")
if not db:
    print("DB is not define")


resume_text = load_text("CV_Developer.pdf")
jd_text = load_text("jd.txt")
thread_id = f"iv-{uuid.uuid4().hex[:8]}"
minutes = 30

with PostgresSaver.from_conn_string(db) as checkpointer:
    checkpointer.setup()
    graph = build_graph(checkpointer)
    config = {"configurable": {"thread_id": thread_id},"callbacks":[langfuse_handler],"metadata": { "langfuse_session_id": thread_id,"langfuse_tags": ["ai-interviewer"]}}
    result = graph.invoke(
            {
                "resume_text": resume_text,
                "jd_text": jd_text,
                "total_seconds": minutes * 60,
            },
            config=config,
    )

    # print(result)

    result = make_json_serializable(result)

    with open("result.json", "w") as f:
        json.dump(result, f, indent=2)
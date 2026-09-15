import os
from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage, HumanMessage
from pydantic import ValidationError
import re
import json 
from dotenv import load_dotenv

load_dotenv()


DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b")
BASE_URL = "https://openrouter.ai/api/v1"

def chat_model(model: str | None = None, temperature: float = 0.4):

    api_key = os.getenv("OPENROUTER_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. On Windows PowerShell:\n"
            '  $env:OPENROUTER_API_KEY = "sk-or-..."\n'
            "or put it in a .env file next to the project."
        )
    name = model or DEFAULT_MODEL
    return init_chat_model(
        model=name,
        model_provider="openrouter",
        api_key=api_key,
        temperature=temperature,
        max_retries=6,
    )


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text

# def structured(llm, schema, system: str, user: str, retries: int = 2):
#     structured_llm = llm.with_structured_output(schema)
#     messages = [SystemMessage(content=system), HumanMessage(content=user)]

#     last_error = ""
#     for attempt in range(retries + 1):
#         try:
#             return structured_llm.invoke(messages)
#         except Exception as exc:
#             last_error = str(exc)[:800]
#             if attempt == retries:
#                 break
#     raise ValueError(f"Model did not return valid {schema.__name__}: {last_error}")

def structured(llm, schema , system: str, user: str, retries: int = 5):

    contract = (
        "Reply with a single JSON object only. No prose, no markdown fences, no "
        "trailing commentary. It must validate against this JSON schema:\n"
        + json.dumps(schema.model_json_schema(), indent=2)
    )
    messages = [
        SystemMessage(content=f"{system}\n\n{contract}"),
        HumanMessage(content=user),
    ]

    last_error = ""
    for attempt in range(retries + 1):
        raw = llm.invoke(messages).content
        if isinstance(raw, list):  # some providers return content blocks
            raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
        try:
            return schema.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)[:800]
            if attempt == retries:
                break
            messages.append(HumanMessage(content=raw if isinstance(raw, str) else ""))
            messages.append(
                HumanMessage(
                    content=(
                        f"That did not validate: {last_error}\n"
                        "Return corrected JSON only."
                    )
                )
            )
    raise ValueError(f"Model did not return valid {schema.__name__}: {last_error}")

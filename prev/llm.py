import os
from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage, HumanMessage
from pydantic import ValidationError
import re
import json
from dotenv import load_dotenv

from agent.prompts import JSON_REPLY_CONTRACT, json_retry_instruction

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

    contract = JSON_REPLY_CONTRACT.format(
        schema=json.dumps(schema.model_json_schema(), indent=2)
    )
    base = [
        SystemMessage(content=f"{system}\n\n{contract}"),
        HumanMessage(content=user),
    ]
    messages = list(base)

    last_error = ""
    for attempt in range(retries + 1):
        raw = llm.invoke(messages).content
        if isinstance(raw, list):  # some providers return content blocks
            raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
        if not isinstance(raw, str):
            raw = ""

        if raw.strip():
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:800]
        else:
            # gpt-oss on OpenRouter intermittently returns empty content;
            # retrying on the original prompt recovers, a poisoned one does not.
            last_error = "model returned an empty response"

        if attempt == retries:
            break

        messages = list(base)
        messages.append(
            HumanMessage(content=json_retry_instruction(last_error))
        )
    raise ValueError(f"Model did not return valid {schema.__name__}: {last_error}")

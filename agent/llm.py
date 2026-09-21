import os
from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage, HumanMessage
from pydantic import ValidationError
import re
import json
from dotenv import load_dotenv
import logging

from agent.prompt import JSON_REPLY_CONTRACT, json_retry_instruction, PROMPT_MAPPING, render_prompt
from agent.langfuse import langfuse

load_dotenv()

DEFAULT_MODEL = os.getenv("MODEL_NAME", "openai/gpt-oss-20b")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openrouter")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", 16000))
_UNFILLED = re.compile(r"\{\{\s*(\w+)\s*\}\}")

def chat_model(model: str | None = None, temperature: float = 0.4):
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError(
            "API_KEY is not set. Put it in a .env file next to the project."
        )

    model_name = model or DEFAULT_MODEL
    provider = MODEL_PROVIDER


    return init_chat_model(
        model=model_name,
        model_provider=provider,
        api_key=api_key,
        temperature=temperature,
        max_retries=6,
        # model_kwargs={
        #     "frequency_penalty": 0.8,
        #     "presence_penalty": 0.5,
        # },
    )

def get_system_prompt(key: str, fallback: str, **vars) -> str:
    """Langfuse prompt for `key` compiled with `vars`; the local copy if Langfuse fails."""
    slug = PROMPT_MAPPING.get(key)
    if slug:
        try:
            compiled = langfuse.get_prompt(slug, label="dev").compile(**vars)
            leftover = _UNFILLED.findall(compiled)
            if not leftover:
                return compiled
            logging.warning("Langfuse prompt %s needs unset variables %s; using local copy", slug, leftover)
        except Exception as e:
            logging.warning("Langfuse fetch failed for %s: %s", slug, e)
    return render_prompt(fallback, **vars)


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text

def structured(llm, schema, system: str, user: str, retries: int = 5):
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
        try:
            response = llm.invoke(messages)
            raw = response.content
        except Exception as exc:
            last_error = f"API Error: {str(exc)}"[:800]
            if attempt == retries:
                break
            continue

        meta = getattr(response, "response_metadata", {}) or {}
        truncated = meta.get("finish_reason") in ("length", "max_tokens") or (
            meta.get("stop_reason") == "max_tokens"
        )

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
            last_error = "model returned an empty response"

        if truncated:
            logging.warning(
                "%s reply hit the output token limit (MAX_OUTPUT_TOKENS=%s)",
                schema.__name__, MAX_OUTPUT_TOKENS,
            )
            last_error = (
                "your reply was cut off because it ran out of output tokens. "
                "Reason briefly, keep every free-text field to one short "
                "sentence, and return the complete JSON object"
            )

        if attempt == retries:
            break

        messages = list(base)
        messages.append(
            HumanMessage(content=json_retry_instruction(last_error))
        )
    raise ValueError(f"Model did not return valid {schema.__name__}: {last_error}")

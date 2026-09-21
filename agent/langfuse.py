from langfuse import get_client
from langfuse.langchain import CallbackHandler

langfuse = get_client()
langfuse_handler = CallbackHandler()

def get_prompt(name: str, label: str = "dev") -> str | None:
    try:
        prompt = langfuse.get_prompt(name, label=label)
        if prompt:
            return prompt.prompt
    except Exception as e:
        print(f"Error fetching prompt {name} from Langfuse: {e}")
    return None

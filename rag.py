import os
import re
from typing import List, Optional
import chromadb
from dotenv import load_dotenv
import json
import urllib.request
import urllib.error
from langchain_google_genai import ChatGoogleGenerativeAI
from ingest import DEFAULT_DB_PATH, get_embedding_function
from models import ActionItem, ActionItemList
from utils import clean_json_markdown

load_dotenv()


class OllamaDirectLLM:
    """
    Direct client for local Ollama.
    Passes think=False to disable verbose chain-of-thought traces on reasoning
    models (like Qwen 3.5 / DeepSeek-R1), enabling fast, direct JSON extraction
    and preventing empty response / token-drop issues.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        temperature: float = 0.0,
        timeout: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def invoke(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        url = f"{self.base_url}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except urllib.error.HTTPError as e:
            # If think parameter is not recognized by older Ollama versions, retry without it
            try:
                del payload["think"]
                fallback_req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(fallback_req, timeout=self.timeout) as fallback_resp:
                    data = json.loads(fallback_resp.read().decode("utf-8"))
                    return data.get("response", "")
            except Exception:
                raise e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Please ensure Ollama is running."
            ) from e


def get_llm(
    provider: str = "gemini",
    model: str = "gemini-1.5-flash",
    temperature: float = 0.0,
    api_key: Optional[str] = None,
):
    """
    Returns an LLM instance based on provider ('gemini' or 'ollama').

    Args:
        provider (str): 'gemini' or 'ollama'.
        model (str): Model name (e.g., 'gemini-1.5-flash' or 'huihui_ai/qwen3.5-abliterated:9b').
        temperature (float): Model temperature. Defaults to 0.0.
        api_key (str, optional): Google API Key (only required for gemini).

    Returns:
        LLM instance.
    """
    if provider == "ollama":
        return OllamaDirectLLM(
            model=model,
            temperature=temperature,
            base_url="http://127.0.0.1:11434",
        )
    else:
        effective_api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not effective_api_key:
            raise ValueError(
                "Google API Key is required for Gemini. Please enter your key in the sidebar or switch LLM Provider to Local Ollama."
            )
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=effective_api_key,
        )


def retrieve_chunks(
    query: str,
    k: int = 8,
    collection_name: str = "documents",
    db_path: str = DEFAULT_DB_PATH,
    embedding_provider: str = "local",
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Connects to the ChromaDB collection and retrieves the top-k most relevant chunk texts.

    Args:
        query (str): The search query.
        k (int): Number of most relevant chunks to return. Defaults to 8.
        collection_name (str): The name of the collection. Defaults to "documents".
        db_path (str): The directory of the ChromaDB persistent client.
        embedding_provider (str): 'local' or 'gemini'.
        api_key (str, optional): API key for gemini embeddings.

    Returns:
        list[str]: The top-k relevant text chunks.
    """
    client = chromadb.PersistentClient(path=db_path)
    embedding_function = get_embedding_function(
        provider=embedding_provider,
        api_key=api_key,
    )

    try:
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_function,
        )
    except Exception:
        return []

    total_docs = collection.count()
    if total_docs == 0:
        return []

    n_results = min(k, total_docs)
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )

    documents = results.get("documents", [])
    if documents and len(documents) > 0:
        return documents[0]
    return []


def extract_actions(
    query: str = "Extract all action items",
    k: int = 8,
    collection_name: str = "documents",
    db_path: str = DEFAULT_DB_PATH,
    embedding_provider: str = "local",
    api_key: Optional[str] = None,
    llm_provider: str = "gemini",
    llm_model: str = "gemini-1.5-flash",
    **kwargs,
) -> List[ActionItem]:
    """
    Extracts action items from document context relevant to the given query.

    1. Retrieves top-k chunks with retrieve_chunks().
    2. Joins them into one context string.
    3. Prompts the selected LLM (Gemini or local Ollama) for structured JSON.
    4. Cleans and validates the JSON output.
    5. Returns the list of validated ActionItem objects.
    """
    chunks = retrieve_chunks(
        query=query,
        k=k,
        collection_name=collection_name,
        db_path=db_path,
        embedding_provider=embedding_provider,
        api_key=api_key,
    )

    if not chunks:
        return []

    context = "\n\n---\n\n".join(chunks)

    prompt = f"""You are an expert action item and task extractor.
Carefully analyze the following document context and extract all concrete action items, assigned tasks, next steps, owners, deadlines, and urgency levels.

Context:
{context}

Query / Focus:
{query}

Format Instructions:
Return ONLY a valid JSON object matching this exact schema:
{{
  "action_items": [
    {{
      "task": "A clear, concise description of what needs to be done",
      "owner": "Name of person or team responsible, or null if unspecified",
      "deadline": "Due date or timeframe, or null if unspecified",
      "priority": "High, Medium, or Low",
      "source": "Exact short quotation or sentence from the context supporting this action item"
    }}
  ]
}}

Rules:
1. Do not invent tasks not mentioned in the context.
2. If priority is not explicitly mentioned, infer reasonable priority (High for critical/urgent, Medium for standard, Low for optional/future).
3. If no action items exist in the context, return {{"action_items": []}}.
4. Return pure JSON without conversational text or preamble.
"""

    llm = get_llm(
        provider=llm_provider,
        model=llm_model,
        temperature=0.0,
        api_key=api_key,
    )

    try:
        response = llm.invoke(prompt)

        # Handle different response types (Chat response vs string)
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, list):
                raw_text = "".join(
                    [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
                )
            else:
                raw_text = str(content)
        else:
            raw_text = str(response)

        from utils import parse_action_items
        items = parse_action_items(raw_text)
        return items

    except Exception as e:
        print(f"Error during action extraction: {e}")
        err_str = str(e)
        if "API_KEY" in err_str or "403" in err_str or "unregistered" in err_str:
            raise ValueError("Google API key is missing or invalid. Please check your key in the sidebar.")
        elif "11434" in err_str or "refused" in err_str:
            raise ValueError("Cannot connect to Ollama. Please ensure Ollama is running at http://localhost:11434.")
        raise ValueError(f"Action extraction encountered an issue: {err_str}")


if __name__ == "__main__":
    test_query = "Extract all action items"
    print(f"Testing chunk retrieval for: '{test_query}'...")
    retrieved = retrieve_chunks(test_query, k=3, embedding_provider="local")
    print(f"Retrieved {len(retrieved)} chunk(s).")

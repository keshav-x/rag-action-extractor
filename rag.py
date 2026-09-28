import os
import re
from typing import List, Optional
import chromadb
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.llms import Ollama
from ingest import DEFAULT_DB_PATH, get_embedding_function
from models import ActionItem, ActionItemList
from utils import clean_json_markdown

load_dotenv()


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
        return Ollama(
            model=model,
            temperature=temperature,
            base_url="http://localhost:11434",
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

        cleaned_json = clean_json_markdown(raw_text)

        # Extract JSON object substring if model returned extra text
        json_match = re.search(r"\{.*\}", cleaned_json, re.DOTALL)
        if json_match:
            cleaned_json = json_match.group(0)

        parsed = ActionItemList.model_validate_json(cleaned_json)
        return parsed.action_items

    except Exception as e:
        print(f"Error during action extraction: {e}")
        raise e


if __name__ == "__main__":
    test_query = "Extract all action items"
    print(f"Testing chunk retrieval for: '{test_query}'...")
    retrieved = retrieve_chunks(test_query, k=3, embedding_provider="local")
    print(f"Retrieved {len(retrieved)} chunk(s).")

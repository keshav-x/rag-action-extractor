import os
import re
import time
import uuid
from typing import Callable, List, Optional
from dotenv import load_dotenv
from pypdf import PdfReader
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from chromadb.utils import embedding_functions
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "chroma_db")


class GoogleGenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Embedding function adapter for ChromaDB using LangChain's GoogleGenerativeAIEmbeddings.
    Includes smart rate-limit retry logic (429 handling with proper backoff duration).
    """

    def __init__(self, model: str = "models/text-embedding-004", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Please add it to your .env file or enter it in the sidebar."
            )
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=self.model,
            google_api_key=self.api_key,
        )

    def __call__(self, input: Documents) -> Embeddings:
        max_retries = 4
        for attempt in range(max_retries):
            try:
                return self.embeddings.embed_documents(input)
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                    # Google Gemini Free Tier 429 returns a retryDelay (often ~40s).
                    # Extract the recommended delay if present, otherwise back off exponentially.
                    delay_match = re.search(r"retry(?:Delay)?[:\s]+'?(\d+)", err_str, re.IGNORECASE)
                    if delay_match:
                        wait_seconds = int(delay_match.group(1)) + 2
                    else:
                        wait_seconds = 42 * (attempt + 1)

                    print(f"[Rate Limit 429] Waiting {wait_seconds}s before retry attempt {attempt + 1}/{max_retries}...")
                    time.sleep(wait_seconds)
                    continue
                raise e


def get_embedding_function(
    provider: str = "local",
    api_key: Optional[str] = None,
    gemini_model: str = "models/text-embedding-004",
):
    """
    Returns the appropriate embedding function based on selected provider.
    - 'local': Uses Chroma's built-in ONNX all-MiniLM-L6-v2 (Zero API calls, no quota limits, fast).
    - 'gemini': Uses Google Generative AI embeddings (requires GOOGLE_API_KEY).
    """
    if provider == "local":
        return embedding_functions.DefaultEmbeddingFunction()
    else:
        return GoogleGenAIEmbeddingFunction(model=gemini_model, api_key=api_key)


def load_document(file_path: str) -> str:
    """
    Loads and extracts text from a document based on its file extension.

    Supported formats:
    - PDF (.pdf) via pypdf
    - DOCX (.docx) via python-docx
    - Text (.txt) via plain text reader

    Args:
        file_path (str): Path to the target document.

    Returns:
        str: The full extracted text content.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".pdf":
        reader = PdfReader(file_path)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text.strip())
        return "\n\n".join(pages_text)

    elif ext == ".docx":
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])

    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported file types are: .pdf, .docx, .txt"
        )


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> List[str]:
    """
    Splits text into chunks using RecursiveCharacterTextSplitter.

    Args:
        text (str): The input text to split.
        chunk_size (int): Size of each chunk in characters. Defaults to 1000.
        chunk_overlap (int): Overlap between adjacent chunks. Defaults to 150.

    Returns:
        list[str]: A list of text chunks.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    return text_splitter.split_text(text)


def reset_collection(collection_name: str = "documents", db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Clears old data by deleting the specified ChromaDB collection before re-ingesting.

    Args:
        collection_name (str): The name of the collection to delete. Defaults to "documents".
        db_path (str): The path to the ChromaDB directory. Defaults to DEFAULT_DB_PATH.
    """
    client = chromadb.PersistentClient(path=db_path)
    try:
        client.delete_collection(name=collection_name)
    except Exception:
        # Collection does not exist or has already been cleared
        pass


def store_chunks(
    chunks: List[str],
    collection_name: str = "documents",
    db_path: str = DEFAULT_DB_PATH,
    embedding_provider: str = "local",
    api_key: Optional[str] = None,
    batch_size: int = 25,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
):
    """
    Stores chunks into ChromaDB in paced batches to prevent Google 429 quota exhaustion.

    Args:
        chunks (list[str]): List of text chunks to embed and store.
        collection_name (str): The name of the collection. Defaults to "documents".
        db_path (str): ChromaDB storage directory path.
        embedding_provider (str): 'local' (recommended, zero rate limits) or 'gemini'.
        api_key (str, optional): Google API Key for gemini embeddings.
        batch_size (int): Number of chunks per embedding batch (default 25).
        progress_callback (callable, optional): Callback for progress updates (current, total, status_text).

    Returns:
        chromadb.Collection: The populated ChromaDB collection object.
    """
    client = chromadb.PersistentClient(path=db_path)
    embedding_function = get_embedding_function(
        provider=embedding_provider,
        api_key=api_key,
    )

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"embedding_provider": embedding_provider},
    )

    if not chunks:
        return collection

    total_chunks = len(chunks)
    total_batches = (total_chunks + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_chunks)
        batch_chunks = chunks[start_idx:end_idx]

        batch_ids = [
            f"{collection_name}_{start_idx + i}_{uuid.uuid4().hex[:6]}"
            for i in range(len(batch_chunks))
        ]

        if progress_callback:
            progress_callback(
                start_idx,
                total_chunks,
                f"Embedding batch {batch_idx + 1}/{total_batches} ({start_idx}-{end_idx} of {total_chunks} chunks)...",
            )

        collection.add(
            documents=batch_chunks,
            ids=batch_ids,
        )

        # Small pacing sleep between batches when using Google API to stay safely under 100 RPM quota
        if embedding_provider == "gemini" and batch_idx < total_batches - 1:
            time.sleep(0.5)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "All chunks embedded and stored successfully!")

    return collection


if __name__ == "__main__":
    sample_file = os.path.join(BASE_DIR, "data", "sample.pdf")
    if os.path.exists(sample_file):
        print(f"Loading {sample_file}...")
        text = load_document(sample_file)
        chunks = chunk_text(text)
        print(f"Created {len(chunks)} chunks.")
        reset_collection("documents")
        store_chunks(chunks, collection_name="documents", embedding_provider="local")
        print(f"Ingestion complete. {len(chunks)} chunks stored.")
    else:
        print(f"Sample file not found at {sample_file}")

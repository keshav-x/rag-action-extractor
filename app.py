import os
import importlib
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

import ingest
import rag
import utils

importlib.reload(ingest)
importlib.reload(rag)
importlib.reload(utils)

from ingest import (
    DEFAULT_DB_PATH,
    load_document,
    chunk_text,
    reset_collection,
    store_chunks,
)
from rag import extract_actions, retrieve_chunks
from utils import (
    action_items_to_df,
    export_to_csv,
    export_to_json,
    export_to_markdown,
    get_priority_label,
)

load_dotenv()

st.set_page_config(
    page_title="Document Action Extractor",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark Slate Professional Theme (No Gradients, No Purple, No Slop)
st.markdown(
    """
    <style>
    /* Base typography & canvas */
    html, body, [data-testid="stAppViewContainer"], .main {
        background-color: #0e1117 !important;
        color: #f0f2f6 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }

    [data-testid="stSidebar"] {
        background-color: #161b22 !important;
        border-right: 1px solid #30363d !important;
    }

    h1, h2, h3, h4 {
        color: #f0f2f6 !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
    }

    p, span, label {
        color: #c9d1d9 !important;
    }

    /* Standard solid primary button (no pill shapes, no harsh gradients) */
    button[kind="primary"] {
        background-color: #238636 !important;
        color: #ffffff !important;
        border: 1px solid rgba(240, 246, 252, 0.1) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.2rem !important;
    }

    button[kind="primary"]:hover {
        background-color: #2ea043 !important;
    }

    button[kind="secondary"] {
        background-color: #21262d !important;
        color: #c9d1d9 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }

    button[kind="secondary"]:hover {
        background-color: #30363d !important;
        color: #ffffff !important;
    }

    /* Result Task Cards (Dark Slate, Clean Border, No Left Stripes) */
    .task-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    .task-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #f0f2f6;
        line-height: 1.4;
        margin-bottom: 6px;
    }

    .task-meta {
        font-size: 0.9rem;
        color: #8b949e;
        margin-bottom: 10px;
    }

    .task-meta strong {
        color: #c9d1d9;
    }

    .source-box {
        background-color: #0d1117;
        border: 1px solid #21262d;
        border-radius: 4px;
        padding: 10px 14px;
        color: #8b949e;
        font-size: 0.88rem;
        line-height: 1.5;
        word-wrap: break-word;
    }

    .source-box strong {
        color: #c9d1d9;
    }

    /* Clean priority tags */
    .badge-high {
        background-color: #3d1b1b;
        color: #ff7b72;
        border: 1px solid #6e2525;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .badge-medium {
        background-color: #3b2a1a;
        color: #e3b341;
        border: 1px solid #6b4c1e;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .badge-low {
        background-color: #1c2b1d;
        color: #7ee787;
        border: 1px solid #234e26;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- SIDEBAR CONFIGURATION -----------------
with st.sidebar:
    st.markdown("### Settings")

    llm_provider_choice = st.radio(
        "LLM Provider",
        options=["Local Ollama", "Google Gemini"],
        index=0,
    )
    llm_provider = "ollama" if llm_provider_choice == "Local Ollama" else "gemini"

    if llm_provider == "gemini":
        env_api_key = os.getenv("GOOGLE_API_KEY", "")
        api_key_input = st.text_input(
            "Google API Key",
            value=st.session_state.get("api_key", env_api_key),
            type="password",
            placeholder="Enter API key",
        )
        if api_key_input:
            st.session_state["api_key"] = api_key_input

        llm_model = st.selectbox(
            "Gemini Model",
            options=["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
            index=0,
        )
    else:
        st.caption("Running locally on device via Ollama.")
        llm_model = st.selectbox(
            "Ollama Model",
            options=["huihui_ai/qwen3.5-abliterated:9b", "qwen2.5:latest", "llama3:latest"],
            index=0,
        )

    st.markdown("---")

    embedding_choice = st.radio(
        "Embedding Engine",
        options=["Local (all-MiniLM-L6-v2)", "Google Gemini"],
        index=0,
    )
    provider_key = "local" if "Local" in embedding_choice else "gemini"

    st.markdown("---")

    top_k = st.slider(
        "Context Chunks (Top-K)",
        min_value=3,
        max_value=20,
        value=8,
    )

    st.markdown("---")
    st.caption("Document Action Extractor")

# ----------------- MAIN INTERFACE -----------------
st.title("Document Action Extractor")
st.markdown("Extract action items, assignees, deadlines, and priorities from unstructured documents.")

# 1. Document Upload
st.markdown("#### 1. Document")
uploaded_file = st.file_uploader(
    "Upload Document",
    type=["pdf", "docx", "txt"],
    label_visibility="collapsed",
)

if uploaded_file is not None:
    current_doc_name = st.session_state.get("ingested_doc_name")
    if current_doc_name != uploaded_file.name:
        with st.status(f"Indexing {uploaded_file.name}...", expanded=False) as status:
            try:
                os.makedirs("data", exist_ok=True)
                file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                temp_path = os.path.join("data", f"uploaded_file{file_ext}")
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                raw_text = load_document(temp_path)
                st.session_state["raw_document_text"] = raw_text

                chunks = chunk_text(raw_text, chunk_size=1000, chunk_overlap=150)
                reset_collection("documents")

                store_chunks(
                    chunks=chunks,
                    collection_name="documents",
                    embedding_provider=provider_key,
                    api_key=st.session_state.get("api_key"),
                    batch_size=25,
                )

                st.session_state["ingested_doc_name"] = uploaded_file.name
                st.session_state["total_chunks"] = len(chunks)
                st.session_state["embedding_provider"] = provider_key
                st.session_state["document_ready"] = True
                status.update(label=f"Indexed {len(chunks)} chunks from {uploaded_file.name}", state="complete", expanded=False)

            except Exception as e:
                status.update(label=f"Indexing failed: {str(e)}", state="error")
                st.error(str(e))

if st.session_state.get("raw_document_text"):
    with st.expander("Document Text Preview"):
        st.text_area(
            "Raw Extracted Text",
            value=st.session_state["raw_document_text"],
            height=140,
            disabled=True,
            label_visibility="collapsed",
        )

st.markdown("<br>", unsafe_allow_html=True)

# 2. Extract Tasks
st.markdown("#### 2. Extraction Query")

# Presets
col_p1, col_p2, col_p3, col_p4 = st.columns(4)
preset_selected = None
if col_p1.button("All Action Items", use_container_width=True):
    preset_selected = "Extract all action items, owners, deadlines, and priority levels."
if col_p2.button("High Priority Only", use_container_width=True):
    preset_selected = "Extract only critical and high priority action items."
if col_p3.button("Upcoming Deadlines", use_container_width=True):
    preset_selected = "Find all action items with specified deadlines or dates."
if col_p4.button("Assigned Tasks", use_container_width=True):
    preset_selected = "Extract all tasks assigned to specific individuals or teams."

col_query, col_btn = st.columns([4, 1])

with col_query:
    default_q = preset_selected or "Extract all action items, owners, deadlines, and priority levels."
    query_input = st.text_input(
        "Query",
        value=default_q,
        placeholder="e.g., Extract all high priority tasks",
        label_visibility="collapsed",
    )

with col_btn:
    extract_clicked = st.button("Extract Tasks", type="primary", use_container_width=True)

if extract_clicked:
    active_key = st.session_state.get("api_key")
    if llm_provider == "gemini" and not active_key:
        st.error("Please enter a Google API Key in the sidebar or switch to Local Ollama.")
    elif not st.session_state.get("document_ready"):
        st.warning("Please upload and index a document first.")
    else:
        with st.spinner("Extracting action items..."):
            try:
                active_provider = st.session_state.get("embedding_provider", "local")
                extracted_items = extract_actions(
                    query=query_input,
                    k=top_k,
                    collection_name="documents",
                    embedding_provider=active_provider,
                    api_key=active_key,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
                st.session_state["extracted_items"] = extracted_items
            except Exception as e:
                st.error(f"Extraction failed: {str(e)}")

# 3. Action Items Results
if "extracted_items" in st.session_state:
    items = st.session_state["extracted_items"]

    st.markdown("<br>", unsafe_allow_html=True)
    if not items:
        st.info("No action items found in the document context for this query.")
    else:
        st.markdown(f"#### 3. Action Items ({len(items)} found)")

        # Toolbar: Filter by priority & Search & Exports
        col_filter, col_search, col_csv, col_json = st.columns([2, 3, 1, 1])

        with col_filter:
            priority_filter = st.selectbox(
                "Filter Priority",
                options=["All Priorities", "High", "Medium", "Low"],
                index=0,
                label_visibility="collapsed",
            )

        with col_search:
            search_query = st.text_input(
                "Search",
                placeholder="Search by keyword, owner, or date...",
                label_visibility="collapsed",
            )

        with col_csv:
            st.download_button(
                label="CSV",
                data=export_to_csv(items),
                file_name="action_items.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_json:
            st.download_button(
                label="JSON",
                data=export_to_json(items),
                file_name="action_items.json",
                mime="application/json",
                use_container_width=True,
            )

        # Filter Logic
        filtered_items = []
        for it in items:
            p_label = get_priority_label(it.priority)
            if priority_filter != "All Priorities" and p_label != priority_filter:
                continue
            if search_query:
                q = search_query.lower()
                text_to_search = f"{it.task} {it.owner or ''} {it.deadline or ''} {it.source}".lower()
                if q not in text_to_search:
                    continue
            filtered_items.append(it)

        if not filtered_items:
            st.caption("No tasks match the selected filter.")
        else:
            for idx, item in enumerate(filtered_items, 1):
                p_label = get_priority_label(item.priority)
                badge_class = (
                    "badge-high" if p_label == "High"
                    else ("badge-medium" if p_label == "Medium" else "badge-low")
                )

                owner_text = item.owner if item.owner else "Unassigned"
                deadline_text = item.deadline if item.deadline else "Not specified"

                st.markdown(
                    f"""
                    <div class="task-card">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div class="task-title">
                                {idx}. {item.task}
                            </div>
                            <span class="{badge_class}">
                                {p_label}
                            </span>
                        </div>
                        <div class="task-meta">
                            <span>Owner: <strong>{owner_text}</strong></span>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <span>Due: <strong>{deadline_text}</strong></span>
                        </div>
                        <div class="source-box">
                            <strong>Source Context:</strong> "{item.source}"
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

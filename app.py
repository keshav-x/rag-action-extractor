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
    page_title="Action Extractor",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Comprehensive Apple Minimal Stylesheet (Light, Cohesive, Uncluttered)
st.markdown(
    """
    <style>
    /* Global Canvas & Base Typography */
    html, body, [data-testid="stAppViewContainer"], .main {
        background-color: #f5f5f7 !important;
        color: #1d1d1f !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }

    /* Streamlit Top Header Bar */
    header[data-testid="stHeader"] {
        background-color: #f5f5f7 !important;
        border-bottom: 1px solid #d2d2d7 !important;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #d2d2d7 !important;
    }
    [data-testid="stSidebar"] * {
        color: #1d1d1f !important;
    }

    /* Main Container Padding */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1000px !important;
    }

    /* Headings */
    h1 {
        font-size: 1.85rem !important;
        font-weight: 600 !important;
        color: #1d1d1f !important;
        letter-spacing: -0.02em !important;
        margin-bottom: 0.2rem !important;
    }

    h2, h3 {
        font-weight: 600 !important;
        color: #1d1d1f !important;
        letter-spacing: -0.01em !important;
    }

    .subtitle {
        color: #6e6e73 !important;
        font-size: 1rem !important;
        margin-bottom: 1.75rem !important;
        line-height: 1.4 !important;
    }

    /* Force Light Background on All Inputs & Uploaders */
    div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    div[data-baseweb="textarea"] {
        background-color: #ffffff !important;
        border: 1px solid #d2d2d7 !important;
        border-radius: 6px !important;
        color: #1d1d1f !important;
    }

    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {
        background-color: #ffffff !important;
        color: #1d1d1f !important;
        font-size: 0.95rem !important;
    }

    /* Dropdowns & Selectboxes */
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 1px solid #d2d2d7 !important;
        border-radius: 6px !important;
        color: #1d1d1f !important;
    }

    div[data-baseweb="select"] * {
        color: #1d1d1f !important;
    }

    /* Native File Uploader - Light Styling */
    [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        border: 1px solid #d2d2d7 !important;
        border-radius: 8px !important;
        padding: 12px !important;
    }

    [data-testid="stFileUploader"] section {
        background-color: #ffffff !important;
        border: 1px dashed #d2d2d7 !important;
        border-radius: 6px !important;
    }

    [data-testid="stFileUploader"] section * {
        color: #1d1d1f !important;
    }

    [data-testid="stFileUploader"] button {
        background-color: #ffffff !important;
        color: #1d1d1f !important;
        border: 1px solid #d2d2d7 !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }

    /* Primary Action Buttons */
    button[kind="primary"] {
        background-color: #0071e3 !important;
        color: #ffffff !important;
        border-radius: 6px !important;
        border: none !important;
        font-weight: 500 !important;
        padding: 0.55rem 1.25rem !important;
    }

    button[kind="primary"]:hover {
        background-color: #0077ed !important;
    }

    /* Secondary Buttons */
    button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #1d1d1f !important;
        border: 1px solid #d2d2d7 !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }

    button[kind="secondary"]:hover {
        background-color: #f5f5f7 !important;
        border-color: #86868b !important;
    }

    /* Content Cards */
    .apple-card {
        background-color: #ffffff;
        border: 1px solid #d2d2d7;
        border-radius: 8px;
        padding: 18px 22px;
        margin-bottom: 12px;
    }

    .apple-quote {
        background-color: #fbfbfd;
        border: 1px solid #e5e5ea;
        border-radius: 6px;
        padding: 10px 14px;
        color: #424245;
        font-size: 0.88rem;
        line-height: 1.5;
        margin-top: 10px;
    }

    /* Priority Badges */
    .priority-badge-high {
        background-color: #fdf2f2;
        color: #b91c1c;
        border: 1px solid #fecaca;
        font-weight: 600;
        font-size: 0.72rem;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    .priority-badge-medium {
        background-color: #fffbeb;
        color: #b45309;
        border: 1px solid #fde68a;
        font-weight: 600;
        font-size: 0.72rem;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    .priority-badge-low {
        background-color: #f0fdf4;
        color: #15803d;
        border: 1px solid #bbf7d0;
        font-weight: 600;
        font-size: 0.72rem;
        padding: 2px 7px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    .meta-item {
        color: #6e6e73;
        font-size: 0.88rem;
    }

    .meta-item strong {
        color: #1d1d1f;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.markdown("### Settings")

    llm_provider_choice = st.radio(
        "Model Provider",
        options=["Local Ollama", "Google Gemini"],
        index=0,
    )
    llm_provider = "ollama" if llm_provider_choice == "Local Ollama" else "gemini"

    if llm_provider == "gemini":
        env_api_key = os.getenv("GOOGLE_API_KEY", "")
        api_key_input = st.text_input(
            "API Key",
            value=st.session_state.get("api_key", env_api_key),
            type="password",
            placeholder="Enter Google API key",
        )
        if api_key_input:
            st.session_state["api_key"] = api_key_input

        llm_model = st.selectbox(
            "Gemini Model",
            options=["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
            index=0,
        )
    else:
        st.caption("Running locally via Ollama.")
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
    st.caption("Action Item Extractor v2.0")

# ----------------- MAIN VIEW -----------------
st.title("Action Item Extractor")
st.markdown("<div class='subtitle'>Upload meeting minutes, transcripts, or specifications to extract assigned tasks, owners, and due dates.</div>", unsafe_allow_html=True)

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
    with st.expander("Preview Extracted Document Text"):
        st.text_area(
            "Raw Text",
            value=st.session_state["raw_document_text"],
            height=140,
            disabled=True,
            label_visibility="collapsed",
        )

st.markdown("<br>", unsafe_allow_html=True)

# 2. Extract Tasks
st.markdown("#### 2. Extraction Query")
col_query, col_btn = st.columns([4, 1])

with col_query:
    query_input = st.text_input(
        "Query",
        value="Extract all action items, owners, deadlines, and priority levels.",
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

        # Filter & Export Toolbar
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
                    "priority-badge-high" if p_label == "High"
                    else ("priority-badge-medium" if p_label == "Medium" else "priority-badge-low")
                )

                owner_text = item.owner if item.owner else "Unassigned"
                deadline_text = item.deadline if item.deadline else "Not specified"

                st.markdown(
                    f"""
                    <div class="apple-card">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div style="font-size: 1.02rem; font-weight: 600; color: #1d1d1f; line-height: 1.4;">
                                {idx}. {item.task}
                            </div>
                            <span class="{badge_class}">
                                {p_label}
                            </span>
                        </div>
                        <div style="margin-bottom: 8px;">
                            <span class="meta-item">Owner: <strong>{owner_text}</strong></span>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <span class="meta-item">Due: <strong>{deadline_text}</strong></span>
                        </div>
                        <div class="apple-quote">
                            <strong>Source:</strong> "{item.source}"
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

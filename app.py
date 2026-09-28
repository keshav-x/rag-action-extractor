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
    page_title="Action Item Extractor",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apple Minimal Design System
st.markdown(
    """
    <style>
    /* Global Background and Typography */
    html, body, [data-testid="stAppViewContainer"], .main {
        background-color: #f5f5f7 !important;
        color: #1d1d1f !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }

    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #d2d2d7 !important;
    }

    /* Clean Apple Header */
    h1 {
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
        color: #1d1d1f !important;
        font-size: 1.85rem !important;
        margin-bottom: 0.25rem !important;
    }

    h2, h3, h4 {
        font-weight: 600 !important;
        color: #1d1d1f !important;
        letter-spacing: -0.01em !important;
    }

    p, span, label {
        color: #1d1d1f !important;
    }

    /* Buttons */
    button[kind="primary"] {
        background-color: #0071e3 !important;
        color: #ffffff !important;
        border-radius: 6px !important;
        border: none !important;
        font-weight: 500 !important;
        padding: 0.45rem 1.1rem !important;
    }

    button[kind="primary"]:hover {
        background-color: #0077ed !important;
    }

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

    /* Clean Card Containers */
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

    .priority-badge-high {
        background-color: #ffe5e5;
        color: #d70015;
        font-weight: 600;
        font-size: 0.75rem;
        padding: 3px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .priority-badge-medium {
        background-color: #fff2d6;
        color: #b25e00;
        font-weight: 600;
        font-size: 0.75rem;
        padding: 3px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .priority-badge-low {
        background-color: #e5f6e8;
        color: #248a3d;
        font-weight: 600;
        font-size: 0.75rem;
        padding: 3px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Muted secondary labels */
    .meta-label {
        color: #86868b;
        font-size: 0.85rem;
    }

    .meta-value {
        color: #1d1d1f;
        font-weight: 500;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- SIDEBAR: SETTINGS -----------------
with st.sidebar:
    st.markdown("### Settings")

    # LLM Engine Selector
    llm_provider_choice = st.radio(
        "Model Provider",
        options=["Local Ollama", "Google Gemini"],
        index=0,
        help="Local Ollama runs offline on your machine. Google Gemini uses cloud inference.",
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
        st.caption("Running locally on device via Ollama.")
        llm_model = st.selectbox(
            "Ollama Model",
            options=["huihui_ai/qwen3.5-abliterated:9b", "qwen2.5:latest", "llama3:latest"],
            index=0,
        )

    st.markdown("---")

    # Embedding Provider Selector
    embedding_choice = st.radio(
        "Embedding Engine",
        options=["Local (all-MiniLM-L6-v2)", "Google Gemini"],
        index=0,
        help="Local runs offline with zero API limits.",
    )
    provider_key = "local" if "Local" in embedding_choice else "gemini"

    st.markdown("---")

    top_k = st.slider(
        "Context Chunks (Top-K)",
        min_value=3,
        max_value=20,
        value=8,
        help="Number of document chunks retrieved for extraction context.",
    )

    st.markdown("---")
    st.caption("Document Action Extractor v2.0")

# ----------------- MAIN WORKSPACE -----------------
st.title("Document Action Extractor")
st.markdown("Upload meeting minutes, transcripts, or specifications to extract assigned tasks, owners, and deadlines.")

# Step 1: Upload Document
col_upload, col_actions = st.columns([3, 2])

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload Document",
        type=["pdf", "docx", "txt"],
        help="Supported formats: PDF, DOCX, TXT.",
        label_visibility="collapsed",
    )

with col_actions:
    if uploaded_file:
        file_size_kb = round(len(uploaded_file.getvalue()) / 1024, 1)
        st.markdown(f"**Selected File:** {uploaded_file.name} ({file_size_kb} KB)")

# Ingestion Processing
if uploaded_file is not None:
    current_doc_name = st.session_state.get("ingested_doc_name")
    if current_doc_name != uploaded_file.name:
        with st.status(f"Processing {uploaded_file.name}...", expanded=True) as status:
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
                status.update(label=f"Error indexing document: {str(e)}", state="error")
                st.error(str(e))

# Document Preview Expander
if st.session_state.get("raw_document_text"):
    with st.expander("Document Text Preview"):
        st.text_area(
            "Extracted Raw Text",
            value=st.session_state["raw_document_text"],
            height=160,
            disabled=True,
            label_visibility="collapsed",
        )

st.markdown("---")

# Step 2: Extract Controls
col_query, col_btn = st.columns([4, 1])

with col_query:
    query_input = st.text_input(
        "Extraction Query",
        value="Extract all action items, owners, deadlines, and priority levels.",
        placeholder="e.g., Extract tasks assigned to engineering team",
        label_visibility="collapsed",
    )

with col_btn:
    extract_clicked = st.button("Extract Actions", type="primary", use_container_width=True)

if extract_clicked:
    active_key = st.session_state.get("api_key")
    if llm_provider == "gemini" and not active_key:
        st.error("Please enter a Google API Key in the sidebar or switch to Local Ollama.")
    elif not st.session_state.get("document_ready"):
        st.warning("Please upload a document first.")
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

# Step 3: Extracted Action Items Results
if "extracted_items" in st.session_state:
    items = st.session_state["extracted_items"]

    if not items:
        st.info("No action items found in the retrieved context.")
    else:
        st.markdown(f"### {len(items)} Action Items")

        # Toolbar: Filter by priority & Search
        col_filter, col_search, col_exp1, col_exp2 = st.columns([2, 3, 1, 1])

        with col_filter:
            priority_filter = st.selectbox(
                "Filter Priority",
                options=["All Priorities", "High", "Medium", "Low"],
                index=0,
                label_visibility="collapsed",
            )

        with col_search:
            search_query = st.text_input(
                "Search tasks or owners",
                placeholder="Search by task name, owner, or date...",
                label_visibility="collapsed",
            )

        with col_exp1:
            csv_bytes = export_to_csv(items)
            st.download_button(
                label="CSV",
                data=csv_bytes,
                file_name="action_items.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_exp2:
            json_str = export_to_json(items)
            st.download_button(
                label="JSON",
                data=json_str,
                file_name="action_items.json",
                mime="application/json",
                use_container_width=True,
            )

        # Apply filtering
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
            st.caption("No action items match the selected filter.")
        else:
            # Display items in clean Apple card layout
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
                            <div style="font-size: 1.05rem; font-weight: 600; color: #1d1d1f; line-height: 1.4;">
                                {idx}. {item.task}
                            </div>
                            <span class="{badge_class}">
                                {p_label}
                            </span>
                        </div>
                        <div style="margin-bottom: 8px;">
                            <span class="meta-label">Owner:</span> <span class="meta-value">{owner_text}</span>
                            &nbsp;&nbsp;&nbsp;&nbsp;
                            <span class="meta-label">Due:</span> <span class="meta-value">{deadline_text}</span>
                        </div>
                        <div class="apple-quote">
                            <strong>Source Context:</strong> "{item.source}"
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

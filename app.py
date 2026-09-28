import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

import importlib
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
    get_priority_emoji,
)

load_dotenv()

st.set_page_config(
    page_title="RAG Action Extractor",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished aesthetics
st.markdown(
    """
    <style>
    .metric-card {
        background: #1e2130;
        border-radius: 8px;
        padding: 12px 18px;
        border: 1px solid #2e344e;
    }
    .stDownloadButton button {
        width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------- SIDEBAR CONFIGURATION -----------------
with st.sidebar:
    st.title("⚙️ Settings & Configuration")

    # LLM Provider Choice: Gemini or Local Ollama
    st.subheader("LLM Provider")
    llm_provider_choice = st.radio(
        "Choose LLM Engine:",
        options=["Google Gemini (Cloud)", "Local Ollama (Offline)"],
        index=0,
        help="Select whether you want to use Google Gemini Flash or your local Qwen Ollama model.",
    )
    llm_provider = "ollama" if "Ollama" in llm_provider_choice else "gemini"

    if llm_provider == "gemini":
        env_api_key = os.getenv("GOOGLE_API_KEY", "")
        api_key_input = st.text_input(
            "Google Gemini API Key",
            value=st.session_state.get("api_key", env_api_key),
            type="password",
            help="Required for Gemini inference. Add to .env or enter here.",
        )
        if api_key_input:
            st.session_state["api_key"] = api_key_input
            st.success("🟢 API Key Ready", icon="✅")
        else:
            st.warning("⚠️ API Key needed for Gemini.", icon="⚠️")

        llm_model = st.selectbox(
            "Gemini Model",
            options=["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
            index=0,
        )
    else:
        st.info("💻 **100% Offline Mode**: Using local Ollama model. No internet or API key required!")
        llm_model = st.selectbox(
            "Local Ollama Model",
            options=["huihui_ai/qwen3.5-abliterated:9b", "qwen2.5:latest", "llama3:latest"],
            index=0,
        )

    st.divider()

    # Embedding Provider Choice
    st.subheader("Embedding Engine")
    embedding_choice = st.radio(
        "Choose Embedding Provider:",
        options=["Local (all-MiniLM-L6-v2)", "Google Gemini (text-embedding-004)"],
        index=0,
        help="Local embeddings run on your CPU with ZERO API quota limits. Recommended to avoid 429 errors.",
    )
    provider_key = "local" if "Local" in embedding_choice else "gemini"

    if provider_key == "local":
        st.info("💡 **Local Mode**: 100% Free, runs offline, zero API quota usage. Never hits 429 rate limits.")
    else:
        st.caption("🌐 **Gemini Mode**: Uses Google GenAI embeddings with paced batching (25 chunks/batch).")

    st.divider()

    top_k = st.slider(
        "Retrieval Chunks (Top-K)",
        min_value=3,
        max_value=25,
        value=8,
        help="Number of relevant document chunks provided to the LLM as context.",
    )

    st.divider()
    st.caption("📋 RAG Document Action Extractor | Class Project")

# ----------------- MAIN CONTENT -----------------
st.title("📋 RAG-Powered Document Action Extractor")
st.markdown(
    """
    Automatically extract actionable items, assignees, deadlines, and urgency levels from
    unstructured documents (PDF, DOCX, TXT) using **Retrieval-Augmented Generation (RAG)**.
    """
)

tab1, tab2 = st.tabs(["1. Upload & Ingest Document", "2. Extract & Analyze Actions"])

# ----------------- TAB 1: UPLOAD & INGEST -----------------
with tab1:
    st.header("1. Upload & Ingest Document")
    st.write("Upload a document to extract its text, chunk it into contextual segments, and index it into ChromaDB.")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Select Document (PDF, DOCX, TXT)",
            type=["pdf", "docx", "txt"],
            help="Upload meeting minutes, project plans, reports, or transcripts.",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        process_btn = st.button("📥 Process & Index Document", type="primary", use_container_width=True)

    if process_btn:
        if uploaded_file is None:
            st.error("Please upload a file first before clicking Process.")
        elif provider_key == "gemini" and not st.session_state.get("api_key"):
            st.error("Google API Key is required for Gemini embeddings. Enter it in the sidebar or switch to Local Embeddings.")
        else:
            try:
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Step 1: Save file
                status_text.text("Saving uploaded file...")
                progress_bar.progress(10)
                os.makedirs("data", exist_ok=True)
                file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                temp_path = os.path.join("data", f"uploaded_file{file_ext}")
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Step 2: Extract text
                status_text.text(f"Extracting text from {uploaded_file.name}...")
                progress_bar.progress(25)
                raw_text = load_document(temp_path)

                if not raw_text.strip():
                    st.warning("No readable text found in document. Please verify the file.")
                else:
                    # Step 3: Chunking
                    status_text.text("Splitting text into overlapping semantic chunks...")
                    progress_bar.progress(40)
                    chunks = chunk_text(raw_text, chunk_size=1000, chunk_overlap=150)

                    # Step 4: Reset DB collection
                    status_text.text("Resetting previous collection in ChromaDB...")
                    progress_bar.progress(50)
                    reset_collection("documents")

                    # Step 5: Store chunks in paced batches with live progress callback
                    def on_batch_progress(curr, total, msg):
                        percent = 50 + int((curr / total) * 45)
                        progress_bar.progress(min(percent, 95))
                        status_text.text(f"Embedding chunks: {msg}")

                    store_chunks(
                        chunks=chunks,
                        collection_name="documents",
                        embedding_provider=provider_key,
                        api_key=st.session_state.get("api_key"),
                        batch_size=25,
                        progress_callback=on_batch_progress,
                    )

                    progress_bar.progress(100)
                    status_text.text("Ingestion completed successfully!")

                    # Save state
                    st.session_state["ingested_doc_name"] = uploaded_file.name
                    st.session_state["total_chunks"] = len(chunks)
                    st.session_state["embedding_provider"] = provider_key
                    st.session_state["document_ready"] = True

                    st.success(f"🎉 Successfully ingested '{uploaded_file.name}' into ChromaDB!")

            except Exception as e:
                st.error(f"❌ Error during ingestion: {str(e)}")
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    st.info("💡 **Tip**: Switch to **'Local (all-MiniLM-L6-v2)'** in the sidebar to bypass Google rate limits completely.")

    # Show Document Status Summary if indexed
    if st.session_state.get("document_ready"):
        st.divider()
        st.subheader("📊 Active Document Status")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Indexed Document", st.session_state.get("ingested_doc_name", "N/A"))
        m2.metric("Total Chunks", st.session_state.get("total_chunks", 0))
        m3.metric("Embedding Engine", st.session_state.get("embedding_provider", "local").title())
        m4.metric("Vector Database", "ChromaDB (Persistent)")


# ----------------- TAB 2: EXTRACT & ANALYZE -----------------
with tab2:
    st.header("2. Extract & Analyze Action Items")
    st.write("Formulate a query or prompt to retrieve relevant document sections and extract assigned actions.")

    # Quick Preset Query Buttons
    st.caption("Quick Presets:")
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    preset_query = None
    if p_col1.button("📋 All Action Items", use_container_width=True):
        preset_query = "Extract all action items, tasks, and deliverables from the document."
    if p_col2.button("🔴 High Priority Tasks", use_container_width=True):
        preset_query = "Extract only high priority or critical action items and urgent tasks."
    if p_col3.button("📅 Deadlines & Due Dates", use_container_width=True):
        preset_query = "Find all action items that have specified deadlines or completion target dates."
    if p_col4.button("👤 Assigned to People", use_container_width=True):
        preset_query = "Extract all tasks that are assigned to specific team members or owners."

    default_query = preset_query or "Extract all action items, owners, deadlines, and priority levels."

    query_input = st.text_input(
        "Extraction Query / Focus",
        value=default_query,
        placeholder="e.g. Extract all tasks assigned to engineering team",
    )

    extract_btn = st.button("🚀 Extract Action Items", type="primary")

    if extract_btn:
        active_key = st.session_state.get("api_key")
        if llm_provider == "gemini" and not active_key:
            st.error("🔑 Google Gemini API Key is required for action extraction. Please enter your key in the sidebar or switch to Local Ollama.")
        elif not st.session_state.get("document_ready"):
            st.warning("⚠️ Please upload and index a document in Tab 1 before extracting action items.")
        else:
            with st.spinner(f"Retrieving top {top_k} chunks and extracting action items via {llm_model} ({llm_provider.title()})..."):
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

    # Display Extracted Items
    if "extracted_items" in st.session_state:
        items = st.session_state["extracted_items"]
        st.divider()

        if not items:
            st.info("No action items were found matching this query in the retrieved context.")
        else:
            # Summary Metrics
            high_count = sum(1 for item in items if item.priority and "high" in item.priority.lower())
            med_count = sum(1 for item in items if item.priority and "med" in item.priority.lower())
            low_count = sum(1 for item in items if item.priority and "low" in item.priority.lower())

            st.subheader(f"✅ Found {len(items)} Action Item(s)")

            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Total Tasks", len(items))
            sm2.metric("High Priority", high_count)
            sm3.metric("Medium Priority", med_count)
            sm4.metric("Low Priority", low_count)

            # Export Buttons
            st.subheader("📥 Export Results")
            exp_col1, exp_col2 = st.columns(2)

            with exp_col1:
                csv_data = export_to_csv(items)
                st.download_button(
                    label="📄 Download as CSV",
                    data=csv_data,
                    file_name="extracted_action_items.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with exp_col2:
                json_data = export_to_json(items)
                st.download_button(
                    label="🧾 Download as JSON",
                    data=json_data,
                    file_name="extracted_action_items.json",
                    mime="application/json",
                    use_container_width=True,
                )

            st.divider()

            # View Mode Selector
            view_mode = st.radio(
                "Display Format:",
                options=["📑 Visual Cards (Full Context & Citations)", "📊 Clean Summary Table"],
                horizontal=True,
            )

            if "Cards" in view_mode:
                st.subheader("📋 Action Items & Source Citations")
                for idx, item in enumerate(items, 1):
                    badge = get_priority_emoji(item.priority)
                    # Color coding for priority border
                    border_color = (
                        "#ff4b4b" if "High" in badge
                        else ("#ffa500" if "Medium" in badge else "#00c853")
                    )

                    st.markdown(
                        f"""
                        <div style="background-color: #1e222d; border-left: 6px solid {border_color}; padding: 18px 22px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.25);">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                                <span style="font-size: 1.15rem; font-weight: 600; color: #ffffff; line-height: 1.4;">
                                    {idx}. {item.task}
                                </span>
                                <span style="background-color: #2a2e3d; padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 0.9rem; white-space: nowrap; margin-left: 15px;">
                                    {badge}
                                </span>
                            </div>
                            <div style="color: #cbd5e1; font-size: 0.95rem; margin-bottom: 12px; line-height: 1.6;">
                                <strong>👤 Owner:</strong> <span style="color: #93c5fd;">{item.owner or 'Unassigned'}</span>
                                &nbsp;&nbsp;•&nbsp;&nbsp;
                                <strong>📅 Deadline:</strong> <span style="color: #fde047;">{item.deadline or 'Not specified'}</span>
                            </div>
                            <div style="background-color: #13161c; padding: 12px 16px; border-radius: 6px; border-left: 3px solid #64748b; color: #e2e8f0; font-size: 0.9rem; line-height: 1.5;">
                                <strong style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Source Evidence from Document:</strong>
                                <em>"{item.source}"</em>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.subheader("📊 Summary Table")
                df = action_items_to_df(items, include_source=False)
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Priority": st.column_config.TextColumn("Priority", width="small"),
                        "Task": st.column_config.TextColumn("Task", width="large"),
                        "Owner": st.column_config.TextColumn("Owner", width="medium"),
                        "Deadline": st.column_config.TextColumn("Deadline", width="medium"),
                    },
                )

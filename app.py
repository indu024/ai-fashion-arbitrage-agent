# app.py
import io
import streamlit as st
import pandas as pd
from gtts import gTTS

# 1. Page configuration
st.set_page_config(
    page_title="AI Fashion Arbitrage Agent",
    page_icon="🛍️",
    layout="wide"
)

# 2. Initialize Session State
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = "session_fashion_1"
if "pending_hitl" not in st.session_state:
    st.session_state["pending_hitl"] = None
if "latest_output" not in st.session_state:
    st.session_state["latest_output"] = None

config = {"configurable": {"thread_id": st.session_state["thread_id"]}}

# 3. Imports from local modules
from agent import app_agent
from database import get_recent_searches, get_connection
from tools import transcribe_audio_bytes, analyze_fashion_image

st.title("🛍️ AI Fashion Arbitrage Agent")
st.caption("Multimodal Search • Dynamic HITL • ChromaDB Semantic Cache • Local MySQL Persistence")

# --- SIDEBAR: MySQL Database History ---
with st.sidebar:
    st.header("🗄️ MySQL Search History")
    history = get_recent_searches(limit=8)
    if history:
        for item in history:
            timestamp, query_text, prod_name, price, store = item
            with st.container(border=True):
                st.caption(f"🕒 {timestamp}")
                st.markdown(f"**Query**: {query_text}")
                if price and float(price) > 0:
                    st.markdown(f"🏷️ Lowest: :green[**₹{price}**] on *{store}*")
                else:
                    st.caption("No price match saved")
    else:
        st.info("No past searches in MySQL yet.")

    st.divider()
    if st.checkbox("View Full Database Table"):
        try:
            conn = get_connection()
            df = pd.read_sql_query("SELECT * FROM search_history ORDER BY id DESC", conn)
            conn.close()
            st.dataframe(df)
        except Exception as e:
            st.error(f"Error loading MySQL table: {e}")

# --- INPUT SECTION (TABS: Text, Voice, Image) ---
tab_text, tab_voice, tab_image = st.tabs(["💬 Text Search", "🎙️ Voice Input", "📷 Image Search"])

query_to_run = None

with tab_text:
    text_query = st.text_input(
        "Enter fashion search:",
        placeholder="e.g. Green Floral Puff-Sleeve Top under ₹700",
        key="input_text"
    )
    if st.button("Search Deals (Text)", type="primary"):
        if text_query.strip():
            query_to_run = text_query.strip()

with tab_voice:
    audio_val = st.audio_input("Speak into your microphone:", key="input_audio")
    if audio_val:
        with st.spinner("🎙️ Transcribing voice..."):
            audio_bytes = audio_val.read()
            query_to_run = transcribe_audio_bytes(audio_bytes)
            st.success(f'Transcribed: "{query_to_run}"')

with tab_image:
    uploaded_img = st.file_uploader(
        "Upload a garment photo or screenshot:",
        type=["jpg", "jpeg", "png", "webp"],
        key="input_image"
    )
    img_budget = st.number_input(
        "Budget Cap (Optional, ₹):",
        min_value=100.0,
        max_value=50000.0,
        value=1500.0,
        step=50.0
    )
    if uploaded_img:
        st.image(uploaded_img, caption="Target Garment", width=180)
        if st.button("Find Matching Deals for Image", type="primary"):
            with st.spinner("🔍 Analyzing garment pattern, cut, and color with Gemini Vision..."):
                img_bytes = uploaded_img.getvalue()
                detected_query = analyze_fashion_image(img_bytes, mime_type=uploaded_img.type)
                query_to_run = f"{detected_query} under {img_budget}"
                st.info(f'Detected Garment: "{detected_query}" (Budget: ₹{img_budget})')

# --- AGENT INITIAL RUN ---
if query_to_run:
    st.session_state["pending_hitl"] = None
    st.session_state["latest_output"] = None
    with st.spinner("Agent evaluating market listings and constraints..."):
        initial_state = {
            "user_query": query_to_run,
            "specs": None,
            "crawled_products": [],
            "matched_groups": [],
            "intervention": None,
            "user_override": None,
            "is_cached": False
        }
        output = app_agent.invoke(initial_state, config=config)

    if output.get("intervention") and output["intervention"].needed:
        st.session_state["pending_hitl"] = output
    else:
        st.session_state["latest_output"] = output

# --- DYNAMIC HUMAN-IN-THE-LOOP (HITL) INTERACTION CARD ---
if st.session_state.get("pending_hitl"):
    hitl_data = st.session_state["pending_hitl"]
    intervention = hitl_data["intervention"]
    specs = hitl_data.get("specs")

    with st.container(border=True):
        st.warning("⚠️ **Agent Needs Your Decision**")
        st.write(intervention.explanation)
        st.info(f"💡 **Suggestion**: {intervention.suggested_fix}")

        # Scenario A: Budget adjustment
        if intervention.issue_type == "budget":
            default_val = 1200.0
            if intervention.suggested_value:
                try:
                    default_val = float(intervention.suggested_value)
                except ValueError:
                    pass

            new_budget = st.number_input(
                "Adjust Budget (₹):",
                min_value=100.0,
                max_value=50000.0,
                value=default_val,
                step=50.0
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Apply Adjusted Budget & Re-run", type="primary"):
                    with st.spinner("Re-evaluating with updated budget..."):
                        resumed = app_agent.invoke({"user_override": {"budget": new_budget}}, config=config)
                        st.session_state["pending_hitl"] = None
                        st.session_state["latest_output"] = resumed
                        st.rerun()
            with col2:
                if st.button("Cancel Search"):
                    st.session_state["pending_hitl"] = None
                    st.rerun()

        # Scenario B: Color choice
        elif intervention.issue_type == "color":
            alt_color = st.text_input("Choose alternative color:", value=intervention.suggested_value or "Black")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Proceed with New Color", type="primary"):
                    with st.spinner("Searching with new color choice..."):
                        resumed = app_agent.invoke({"user_override": {"color": alt_color}}, config=config)
                        st.session_state["pending_hitl"] = None
                        st.session_state["latest_output"] = resumed
                        st.rerun()
            with col2:
                if st.button("Cancel Search"):
                    st.session_state["pending_hitl"] = None
                    st.rerun()

        # Scenario C: Broad / Zero results
        else:
            updated_query = st.text_input("Refine Search Terms:", value=specs.search_query if specs else "")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Retry with Refined Query", type="primary"):
                    with st.spinner("Re-searching..."):
                        retry_state = {
                            "user_query": updated_query,
                            "specs": None,
                            "crawled_products": [],
                            "matched_groups": [],
                            "intervention": None,
                            "user_override": None,
                            "is_cached": False
                        }
                        resumed = app_agent.invoke(retry_state, config=config)
                        st.session_state["pending_hitl"] = None
                        st.session_state["latest_output"] = resumed
                        st.rerun()
            with col2:
                if st.button("Cancel Search"):
                    st.session_state["pending_hitl"] = None
                    st.rerun()

# --- DISPLAY MATCHED RESULTS ---
if st.session_state.get("latest_output") and not st.session_state.get("pending_hitl"):
    output = st.session_state["latest_output"]
    specs = output.get("specs")
    groups = output.get("matched_groups", [])
    is_cached = output.get("is_cached", False)

    if is_cached:
        st.success("⚡ **Fast Result**: Retrieved via **ChromaDB Semantic Cache** (Zero API calls)")

    if specs:
        st.markdown(
            f"**Specs Evaluated:** Category: `{specs.category}` | Color: `{specs.color}` | "
            f"Style: `{specs.sleeve_type}` | Budget: `₹{specs.max_budget}`"
        )

    if not groups:
        st.info("No matching item groups found for the specified constraints.")
    else:
        st.subheader(f"Found {len(groups)} Item Matches Across Stores")

        best_deal = min(groups, key=lambda x: x.lowest_price)
        speech_text = f"I found {len(groups)} matches. The best price is {best_deal.lowest_price} rupees on {best_deal.cheapest_store}."

        try:
            tts = gTTS(text=speech_text, lang='en')
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            st.audio(audio_buffer, format="audio/mp3", autoplay=True)
        except Exception:
            pass

        for group in groups:
            with st.expander(f"✨ {group.product_name} — Lowest: ₹{group.lowest_price} on {group.cheapest_store}", expanded=True):
                st.caption(f"**Why they match**: {group.reasoning}")
                cols = st.columns(len(group.stores))
                for col, store_item in zip(cols, group.stores):
                    with col:
                        if store_item.thumbnail:
                            st.image(store_item.thumbnail, width=130)
                        st.markdown(f"**{store_item.source}**")
                        if store_item.price_inr == group.lowest_price:
                            st.markdown(f":green[**₹{store_item.price_inr} (Cheapest)**]")
                        else:
                            st.markdown(f"₹{store_item.price_inr}")
                        st.caption(store_item.title[:60] + "...")
                        st.link_button("Buy Link", store_item.link)
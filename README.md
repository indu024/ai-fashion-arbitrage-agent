# Multimodal Fashion Arbitrage and Discovery Agent

An e-commerce aggregation agent that matches clothing items across major Indian retail platforms including Myntra, AJIO, Nykaa, and Amazon to find the lowest price. It accepts text, voice recordings, and garment photos, using LangGraph to coordinate multimodal parsing, semantic caching, and dynamic human-in-the-loop decisions.

---

## Tech Stack

- Core Language: Python 3.10+ — Primary programming language powering the agent pipeline, scraping tools, and UI.
- Agent Orchestration: LangGraph — Multi-node workflow engine (`StateGraph`, `MemorySaver`) managing state transitions, conditional routing, and Human-in-the-Loop (HITL) checkpoints.
- LLM Framework: LangChain (`langchain-core`, `langchain-google-genai`) — Interfaces with Gemini models and enforces structured JSON output schemas (`with_structured_output`).
- Multimodal AI Models: Google Gemini 3.7 Flash — Powers query spec normalization, cross-store garment deduplication, deal arbitrage, visual fashion analysis, and audio transcription.
- Native GenAI SDK: Google GenAI SDK (`google-genai`) — Direct binary multimodal processing for uploaded garment images and voice recordings.
- Web UI & Dashboard: Streamlit — Interactive frontend featuring text input, microphone voice recording, garment photo upload, dynamic HITL decision prompts, and history logs.
- Semantic Vector Cache: ChromaDB — Vector database for caching search queries using cosine similarity (0.85+ threshold) and a 24-hour TTL expiration to reduce redundant API calls.
- Relational Database: MySQL (via `PyMySQL`) — Relational audit trail storing search history, parsed criteria, pricing details, and store links.
- E-Commerce Search Engine: Serper API — Real-time Google Shopping India query engine aggregating listings across major platforms (Amazon, Myntra, AJIO, Nykaa, etc.).
- Data Validation & Schemas: Pydantic (v2) — Type safety and data modeling (`ExtractedSpecs`, `StoreProduct`, `MatchedGroup`, `HumanIntervention`).
- Speech Synthesis: gTTS (Google Text-to-Speech) — Audio voiceover generation for speaking out top deals.
- Data & Utilities: pandas, Requests, python-dotenv — Dataframe inspection, HTTP networking, and `.env` secret management.

---

## Architecture Overview


               +----------------------------------------+
               | User Input: Text, Audio, or Photo      |
               +-------------------+--------------------+
                                   |
                                   v
               +----------------------------------------+
               | Node 1: Spec Normalization             |
               | - Extract style, cut, color, max budget|
               | - Multimodal Gemini vision / audio STT |
               +-------------------+--------------------+
                                   |
                                   v
               +----------------------------------------+
               | Node 2: Retrieval & Semantic Caching   |
               | - Check ChromaDB vector embeddings     |
               |   -> Hit: Return cached deal (0 APIs)  |
               |   -> Miss: Scrape live store APIs      |
               +-------------------+--------------------+
                                   |
                                   v
               +----------------------------------------+
               | Node 3: Market Constraint Evaluator    |
               +-------------------+--------------------+
                                   |
                     Are constraints satisfied?
                                  / \
                     No (Mismatch)   Yes (Matches Found)
                                /     \
                               v       v
+-------------------------------+     +-------------------------------+
| Node 4: Human-in-the-Loop     |     | Node 5: Matcher & Deduplicator|
| - Pause graph via MemorySaver |     | - Group identical garments    |
| - Present actionable choices: |     | - Find lowest cross-store rate|
|   adjust budget, swap color   |     +---------------+---------------+
+---------------+---------------+                     |
                |                                     +------------+
                | Resume via user override                         |
                +------------------------------------------------->|
                                                                   v
                                              +--------------------+--------------------+
                                              | Dual Storage Persistence Layer          |
                                              | - MySQL: Search logs and audit history  |
                                              | - ChromaDB: Embed query and top deal    |
                                              +-----------------------------------------+


## System feature 

1.Multimodal Search Ingestion

Text: Parses natural language requests into structured specifications.

Voice Assistant: Accepts spoken queries, transcribes them via Gemini Flash, and speaks the lowest price back to the user using gTTS.

Image Recognition: Analyzes garment photos or screenshots to extract pattern, cut, color, and silhouette without manual typing.

2.ChromaDB Semantic Caching

Evaluates search intent using vector embeddings.

Recognizes that "baggy black denim" and "black loose-fit jeans" represent the same query.

Returns cached deals under 24 hours old with zero external API calls.

3.Dynamic Human-in-the-Loop (HITL)

When constraints fail (e.g., target budget is ₹500, but the market floor is ₹799, or an exact color is unavailable), the agent pauses state execution.

Generates an interactive prompt for the user to adjust the budget, pick an available color, or refine keywords, then resumes seamlessly using LangGraph memory checkpoints.

4.MySQL Search History & Audit Logging

Automatically writes every query, extracted specification, matched products, lowest price, and store URL into a local MySQL relational database.

Sidebar features live history cards and a full database table viewer.


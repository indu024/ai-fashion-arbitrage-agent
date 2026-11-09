# agent.py
import os
from typing import List, TypedDict, Optional
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI

from schemas import ExtractedSpecs, StoreProduct, MatchedGroup, HumanIntervention
from tools import search_stores
from database import init_db, save_search_result
from vector_store import find_cached_deal, cache_search_result

load_dotenv()
init_db()

# Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-3.7-flash",
    temperature=0.1
)

# 1. State Definition
class AgentState(TypedDict):
    user_query: str
    specs: Optional[ExtractedSpecs]
    crawled_products: List[StoreProduct]
    matched_groups: List[MatchedGroup]
    intervention: Optional[HumanIntervention]
    user_override: Optional[dict]
    is_cached: bool

# Node 1: Normalizer (Extracts search specs and applies human overrides)
def normalize_spec_node(state: AgentState):
    user_q = state["user_query"]

    extractor = llm.with_structured_output(ExtractedSpecs)
    prompt = (
        f"You are an expert e-commerce search assistant. Extract attributes and generate a concise "
        f"search query from: '{user_q}'"
    )
    specs: ExtractedSpecs = extractor.invoke(prompt)

    # Apply any overrides from human intervention
    if state.get("user_override"):
        overrides = state["user_override"]
        if "budget" in overrides:
            specs.max_budget = float(overrides["budget"])
        if "color" in overrides:
            specs.color = overrides["color"]
            specs.search_query = f"{specs.color} {specs.category}"

    return {"specs": specs, "intervention": None, "is_cached": False}

# Node 2: Crawler (Checks ChromaDB semantic cache first, falls back to web crawl)
def crawl_stores_node(state: AgentState):
    query = state["user_query"]
    specs = state["specs"]

    # 1. Check ChromaDB Semantic Cache (if user hasn't forced an override)
    if not state.get("user_override"):
        cached_deal = find_cached_deal(query, similarity_threshold=0.85)
        if cached_deal:
            print("\n" + "="*50)
            print(f"🟢 [CHROMA CACHE HIT] Served from Vector DB!")
            print(f"   Query: '{query}'")
            print(f"   Matched Title: {cached_deal['product_title']}")
            print(f"   Price: ₹{cached_deal['price']} on {cached_deal['store']}")
            print(f"   Similarity Score: {cached_deal['relevance_score']}")
            print("="*50 + "\n")
            cached_product = StoreProduct(
                source=cached_deal["store"],
                title=cached_deal["product_title"],
                price_inr=cached_deal["price"],
                link=cached_deal["link"],
                thumbnail=None
            )
            return {"crawled_products": [cached_product], "is_cached": True}
            
    print("\n" + "="*50)
    print(f"🔴 [CACHE MISS -> LIVE API] Calling Serper / External Stores...")
    print(f"   Search Query: '{specs.search_query}'")
    print("="*50 + "\n")
    # 2. Live crawl via Serper if no cache hit
    products = search_stores(specs.search_query, max_budget=None)
    return {"crawled_products": products, "is_cached": False}

# Node 3: Dynamic Evaluator (Checks budget, color, and relevance for HITL)
def evaluate_market_node(state: AgentState):
    # Skip evaluation if it was retrieved directly from cache or already overridden
    if state.get("is_cached") or state.get("user_override"):
        return {"intervention": HumanIntervention(
            needed=False, 
            issue_type="none", 
            explanation="", 
            suggested_fix="", 
            suggested_value=None
        )}

    specs = state["specs"]
    products = state["crawled_products"]

    if not products:
        return {
            "intervention": HumanIntervention(
                needed=True,
                issue_type="zero_results",
                explanation=f"No online listings found for '{specs.search_query}'.",
                suggested_fix="Try broadening your keywords or removing specific constraints.",
                suggested_value=""
            )
        }

    evaluator = llm.with_structured_output(HumanIntervention)
    summary_list = [f"[{p.source}] {p.title} - ₹{p.price_inr}" for p in products[:8]]
    
    prompt = f"""
Target Specifications:
- Category: {specs.category}
- Color: {specs.color}
- Max Budget: ₹{specs.max_budget}

Items found on Indian stores:
{chr(10).join(summary_list)}

Task:
Determine if valid products exist that satisfy the user's budget and color.
1. If several items match and are under the budget (₹{specs.max_budget}), set needed=False.
2. If items exist for this garment but all exceed the budget, set needed=True, issue_type='budget', state lowest found price in explanation, and suggest increasing budget.
3. If the requested color is completely unavailable, set needed=True, issue_type='color', explain available colors, and suggest an alternative.
"""
    intervention = evaluator.invoke(prompt)
    return {"intervention": intervention}

# Conditional Routing Edge
def route_after_evaluation(state: AgentState) -> str:
    intervention = state.get("intervention")
    if intervention and intervention.needed:
        return "ask_human"
    return "proceed_to_match"

# Node 4: Matcher Node (Deduplication, MySQL Logging & ChromaDB Caching)
def match_and_arbitrage_node(state: AgentState):
    specs = state["specs"]
    products = state["crawled_products"]

    # If it was a cache hit, bypass LLM deduplication
    if state.get("is_cached") and products:
        cached_p = products[0]
        group = MatchedGroup(
            product_name=cached_p.title,
            reasoning="Retrieved directly from ChromaDB Semantic Cache.",
            cheapest_store=cached_p.source,
            lowest_price=cached_p.price_inr,
            stores=[cached_p]
        )
        return {"matched_groups": [group]}

    # Enforce budget constraint
    if specs and specs.max_budget:
        products = [p for p in products if p.price_inr <= specs.max_budget]

    if not products:
        save_search_result(state["user_query"], specs, [])
        return {"matched_groups": []}

    item_summaries = [f"ID {i}: [{p.source}] {p.title} - Price: ₹{p.price_inr}" for i, p in enumerate(products)]
    prompt = f"""
You are an expert product deduplicator. Group identical items across stores:
{chr(10).join(item_summaries)}
"""
    from pydantic import BaseModel, Field

    class RawMatchGroup(BaseModel):
        unified_name: str
        item_ids: List[int]
        reasoning: str

    class DeduplicationResult(BaseModel):
        groups: List[RawMatchGroup]

    matcher = llm.with_structured_output(DeduplicationResult)
    result = matcher.invoke(prompt)

    final_groups = []
    for g in result.groups:
        matched_stores = [products[idx] for idx in g.item_ids if idx < len(products)]
        if matched_stores:
            cheapest = min(matched_stores, key=lambda x: x.price_inr)
            final_groups.append(
                MatchedGroup(
                    product_name=g.unified_name,
                    reasoning=g.reasoning,
                    cheapest_store=cheapest.source,
                    lowest_price=cheapest.price_inr,
                    stores=matched_stores
                )
            )

    # 1. Save Relational Search History in MySQL
    save_search_result(state["user_query"], specs, final_groups)

    # 2. Cache Top Deal in ChromaDB Vector Database
    if final_groups:
        top_deal = min(final_groups, key=lambda x: x.lowest_price)
        cheapest_item = min(top_deal.stores, key=lambda s: s.price_inr)
        cache_search_result(
            query=state["user_query"],
            product_title=top_deal.product_name,
            price=top_deal.lowest_price,
            store=top_deal.cheapest_store,
            link=cheapest_item.link
        )

    return {"matched_groups": final_groups}

# Assemble LangGraph
builder = StateGraph(AgentState)
builder.add_node("normalizer", normalize_spec_node)
builder.add_node("crawler", crawl_stores_node)
builder.add_node("evaluator", evaluate_market_node)
builder.add_node("matcher", match_and_arbitrage_node)

builder.add_edge(START, "normalizer")
builder.add_edge("normalizer", "crawler")
builder.add_edge("crawler", "evaluator")

builder.add_conditional_edges(
    "evaluator",
    route_after_evaluation,
    {
        "ask_human": END,
        "proceed_to_match": "matcher"
    }
)

builder.add_edge("matcher", END)

# MemorySaver for HITL state pause and resume
memory = MemorySaver()
app_agent = builder.compile(checkpointer=memory)
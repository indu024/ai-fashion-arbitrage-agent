# In vector_store.py
import time

CACHE_EXPIRY_HOURS = 24  # Expire cached prices after 24 hours

def cache_search_result(query: str, product_title: str, price: float, store: str, link: str):
    text_to_embed = f"Search: {query} | Best Match: {product_title}"
    metadata = {
        "original_query": query,
        "product_title": product_title,
        "price": float(price),
        "store": store,
        "link": link,
        "cached_at": time.time()  # Store current Unix timestamp
    }
    vectorstore.add_texts(texts=[text_to_embed], metadatas=[metadata])

def find_cached_deal(query: str, similarity_threshold: float = 0.80):
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=1)
        if not results:
            return None
        
        doc, score = results[0]
        cached_at = doc.metadata.get("cached_at", 0)
        age_in_hours = (time.time() - cached_at) / 3600

        # Check if score matches AND cache is not expired
        if score >= similarity_threshold:
            if age_in_hours > CACHE_EXPIRY_HOURS:
                print(f"⚠️ [CACHE EXPIRED] Record is {round(age_in_hours, 1)}h old. Re-fetching live API.")
                return None
            return {
                "matched_from_cache": True,
                "relevance_score": round(score, 2),
                **doc.metadata
            }
        return None
    except Exception as e:
        print(f"[CACHE] ChromaDB query error: {e}")
        return None
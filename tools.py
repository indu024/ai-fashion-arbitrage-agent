# tools.py
import os
import re
import requests
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from schemas import StoreProduct

load_dotenv()

# --- TOOL 1: Web Store Crawler Tool ---
def search_stores(query: str, max_budget: float = None) -> List[StoreProduct]:
    """Queries Serper Google Shopping for Indian store listings."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("[WARNING] SERPER_API_KEY missing.")
        return []

    url = "https://google.serper.dev/shopping"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": f"{query} India", "gl": "in", "hl": "en", "num": 10}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        raw_items = data.get("shopping", [])
    except Exception as e:
        print(f"[ERROR] Serper search failed: {e}")
        return []

    products = []
    for item in raw_items:
        raw_price = item.get("price", "0")
        clean_price = re.sub(r"[^\d.]", "", raw_price)
        price_val = float(clean_price) if clean_price else 0.0

        if max_budget and price_val > max_budget:
            continue

        products.append(
            StoreProduct(
                source=item.get("source", "Online Store"),
                title=item.get("title", ""),
                price_inr=price_val,
                link=item.get("link", "#"),
                thumbnail=item.get("imageUrl")
            )
        )
    return products


# --- TOOL 2: Visual Search Tool ---
def analyze_fashion_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Analyzes an uploaded garment image and converts visual attributes into a search query."""
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    prompt = """
    You are an expert fashion stylist and e-commerce visual search assistant.
    Analyze the uploaded garment image and generate a precise e-commerce search query.
    
    Identify:
    - Garment Category (e.g., Top, Dress, Trousers, Kurti)
    - Color and shade (e.g., Olive Green, Dusty Pink, Navy Blue)
    - Pattern/Print (e.g., Floral, Solid, Striped, Abstract)
    - Specific style cuts or features (e.g., Puff Sleeve, Sweetheart Neck, Pleated, Wide-Leg)
    
    Format: Return ONLY the search query string in lowercase words without punctuation.
    Example: "olive green floral print square neck puff sleeve top"
    """

    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt
        ]
    )
    return response.text.strip().replace('"', '')


# --- TOOL 3: Voice Transcription Tool ---
def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """Takes WAV audio bytes and transcribes speech to plain text using Gemini."""
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
            "Transcribe this audio query accurately into plain text. Only return the transcript text."
        ]
    )
    return response.text.strip()
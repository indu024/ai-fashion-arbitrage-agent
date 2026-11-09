# schemas.py
from typing import Optional, List
from pydantic import BaseModel, Field

class ExtractedSpecs(BaseModel):
    category: str = Field(description="e.g., Western Top, Crop Top, Shirt")
    color: Optional[str] = Field(default="", description="e.g., Green, Olive, Blue")
    pattern: Optional[str] = Field(default="", description="e.g., Floral, Striped, Solid")
    sleeve_type: Optional[str] = Field(default="", description="e.g., Puff Sleeve, Sleeveless")
    max_budget: Optional[float] = Field(default=None, description="Budget cap in INR")
    search_query: str = Field(description="Optimized search query for shopping engines")

class StoreProduct(BaseModel):
    title: str
    source: str
    price_inr: float
    link: str
    thumbnail: Optional[str] = ""

class MatchedGroup(BaseModel):
    product_name: str
    reasoning: str
    cheapest_store: str
    lowest_price: float
    stores: List[StoreProduct]

class HumanIntervention(BaseModel):
    needed: bool = Field(description="True if human adjustment is needed because no valid products fit all criteria")
    issue_type: str = Field(description="Type of bottleneck: 'budget', 'color', 'style', or 'zero_results'")
    explanation: str = Field(description="Friendly explanation to show the user describing what went wrong")
    suggested_fix: str = Field(description="Actionable suggestion (e.g., 'Increase budget to ₹850' or 'Switch color to Olive')")
    suggested_value: Optional[str] = Field(description="The concrete suggested value, e.g., '850' or 'Blue'")
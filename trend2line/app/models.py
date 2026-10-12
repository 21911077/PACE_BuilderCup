"""Typed contracts. Models used as Gemini response schemas avoid dict-typed fields."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

ProcessStep = Literal[
    "tempering", "solid_moulding", "shell_moulding", "filling_deposit", "backing_off",
    "toasting", "cooling", "demoulding", "wrapping", "enrobing", "mixing",
    "liquid_filling", "baking", "frying", "other",
]
ProductFormat = Literal[
    "solid_bar", "shell_and_fill", "enrobed_bar", "bite", "beverage", "bakery", "other",
]


class ArticleChoice(BaseModel):
    title: str = Field(description="Exactly one of the candidate titles")
    reason: str


class SpecIngredient(BaseModel):
    name: str = Field(description="Ingredient as a person would write it")
    ingredient_id: str = Field(description="ID from the provided vocabulary, or 'other'")
    role: Literal["shell", "filling", "inclusion", "coating", "base", "topping", "other"] = "other"


class ProductSpec(BaseModel):
    product_name: str = Field(description="Descriptive product name")
    format: ProductFormat
    ingredients: list[SpecIngredient]
    process_steps: list[ProcessStep]
    notes: str = ""


class Claim(BaseModel):
    text: str
    kind: Literal["numeric", "date", "process", "regulatory", "speculative"]
    evidence_ids: list[str] = Field(default_factory=list)
    field: Optional[str] = Field(default=None, description="Dot path into the cited evidence payload")
    value: Optional[float] = None
    date_value: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    line: Optional[str] = None
    capability: Optional[str] = None
    capability_present: Optional[bool] = None
    rule_id: Optional[str] = None


class Plan(BaseModel):
    headline: str
    rationale: str
    actions: list[str]
    claims: list[Claim]

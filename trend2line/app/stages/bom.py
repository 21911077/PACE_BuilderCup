"""BOM Morph: pure set logic over canonical ingredient IDs."""
from ..models import ProductSpec


def bom_diff(our_sku: dict, spec: ProductSpec, allergen_map: dict[str, dict]) -> dict:
    ours = set(our_sku["ingredients"])
    theirs = {i.ingredient_id for i in spec.ingredients if i.ingredient_id in allergen_map}
    unmapped = sorted({i.name for i in spec.ingredients if i.ingredient_id not in allergen_map})

    def allergens_of(ids: set[str]) -> set[str]:
        return {a for i in ids for a in allergen_map[i]["allergens"]}

    product_allergens = allergens_of(theirs)
    our_allergens = allergens_of(ours)
    return {
        "our_sku": our_sku["name"],
        "added_ingredients": sorted(theirs - ours),
        "removed_ingredients": sorted(ours - theirs),
        "kept_ingredients": sorted(ours & theirs),
        "unmapped_ingredients": unmapped,
        "product_allergens": sorted(product_allergens),
        "new_allergens_vs_our_sku": sorted(product_allergens - our_allergens),
        "format_from": our_sku["format"],
        "format_to": spec.format,
        "format_change": our_sku["format"] != spec.format,
        "new_process_steps": sorted(set(spec.process_steps) - set(our_sku["process_steps"])),
    }

from warden.mandates.schema import CartMandate, IntentMandate


def check_constraints(intent_mandate: IntentMandate, cart_mandate: CartMandate) -> list[str]:
    violations = []
    # A reconstructed cart without explicit buyer agreement is not an
    # authorization.  Keep this separate from price/category checks so
    # evaluation can attribute a rejection correctly.
    if getattr(cart_mandate, "agreement_status", "agreed") != "agreed":
        violations.append("agreement_ambiguous")
    if not cart_mandate.items and getattr(cart_mandate, "agreement_status", "agreed") != "agreed":
        violations.append("cart_empty")
    if cart_mandate.total > intent_mandate.max_price:
        violations.append("price_ceiling_exceeded")
    if cart_mandate.category.lower() not in [c.lower() for c in intent_mandate.allowed_categories]:
        violations.append("category_mismatch")
    for red_line in intent_mandate.red_lines:
        if (
            red_line.lower() == "no subscriptions"
            and "subscription" in str(cart_mandate.items).lower()
            or red_line.lower() == "no auto-renew"
            and any(
                "auto-renew" in str(item).lower() or "recurring" in str(item).lower() for item in cart_mandate.items
            )
        ):
            violations.append(f"red_line_violated:{red_line}")
    return violations

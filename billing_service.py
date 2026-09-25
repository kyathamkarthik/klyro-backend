def calculate_klyro_credits_from_ai_cost(actual_openai_cost: float, target_ai_budget: float, package_credits: float) -> float:
    """
    Converts actual AI cost into Klyro Credits based on the user's package ratio.
    """
    if target_ai_budget <= 0:
        return 0.0
    
    klyro_credits_used = (actual_openai_cost / target_ai_budget) * package_credits
    return round(klyro_credits_used, 4)
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Conservative mixed Chinese/English estimate used before provider tokenization."""
    chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other = max(0, len(text) - chinese)
    return max(1, chinese + (other + 3) // 4)


@dataclass(frozen=True)
class BudgetedPrompt:
    system_prompt: str
    user_prompt: str
    estimated_tokens: int
    truncated: bool


def _truncate_to_tokens(text: str, budget: int, marker: str = "") -> str:
    """Return the longest prefix whose conservative estimate fits the budget."""
    if budget <= 0:
        return ""
    marker = marker if estimate_tokens(marker) < budget else ""
    content_budget = max(0, budget - (estimate_tokens(marker) if marker else 0))
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(text[:middle]) <= content_budget:
            low = middle
        else:
            high = middle - 1
    return text[:low] + marker


def fit_prompt(system_prompt: str, user_prompt: str, max_tokens: int) -> BudgetedPrompt:
    """Fit both prompt parts into a hard, conservative token ceiling."""
    max_tokens = max(2, max_tokens)
    current = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
    if current <= max_tokens:
        return BudgetedPrompt(system_prompt, user_prompt, current, False)

    # Always retain at least one token for each prompt part.
    system_budget = min(estimate_tokens(system_prompt), max(1, max_tokens // 3))
    fitted_system = _truncate_to_tokens(system_prompt, system_budget)
    remaining = max(1, max_tokens - estimate_tokens(fitted_system))
    fitted_user = _truncate_to_tokens(
        user_prompt,
        remaining,
        marker="\n\n[上下文已按 Token 预算截断]",
    )
    total = estimate_tokens(fitted_system) + estimate_tokens(fitted_user)
    return BudgetedPrompt(fitted_system, fitted_user, total, True)

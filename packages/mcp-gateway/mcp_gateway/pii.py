"""PII masking — detect and mask sensitive data in tool arguments/responses."""
from __future__ import annotations

import re
from typing import Any

from .schemas import ToolCallResponse


class PIIPattern:
    """A PII detection pattern with regex and replacement."""

    def __init__(self, name: str, pattern: str, replacement: str) -> None:
        self.name = name
        self.pattern = pattern
        self.replacement = replacement
        self._compiled = re.compile(pattern)


def _luhn_check(number: str) -> bool:
    """Validate a number string using the Luhn algorithm.

    Args:
        number: Digits-only string.

    Returns:
        True if valid Luhn checksum.
    """
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# Built-in PII patterns
_CHINESE_ID_PATTERN = PIIPattern(
    name="chinese_id_card",
    pattern=(
        r"\b[1-9]\d{5}"
        r"(?:18|19|20)\d{2}"
        r"(?:0[1-9]|1[0-2])"
        r"(?:0[1-9]|[12]\d|3[01])"
        r"\d{3}[\dXx]\b"
    ),
    replacement="[ID_MASKED]",
)

_BANK_CARD_PATTERN = PIIPattern(
    name="bank_card",
    pattern=r"\b\d{15,19}\b",
    replacement="[CARD_MASKED]",
)


class PIIMasker:
    """Masks PII in strings and dicts."""

    def __init__(
        self, extra_patterns: list[PIIPattern] | None = None
    ) -> None:
        self._patterns = [_CHINESE_ID_PATTERN, _BANK_CARD_PATTERN]
        if extra_patterns:
            self._patterns.extend(extra_patterns)

    def mask_string(self, text: str) -> tuple[str, int]:
        """Mask PII in a string.

        Args:
            text: Input string.

        Returns:
            Tuple of (masked_string, count_of_replacements).
        """
        total_count = 0
        result = text

        # Chinese ID card (always mask, no Luhn needed)
        id_matches = _CHINESE_ID_PATTERN._compiled.findall(result)
        if id_matches:
            result = _CHINESE_ID_PATTERN._compiled.sub(
                _CHINESE_ID_PATTERN.replacement, result
            )
            total_count += len(id_matches)

        # Bank card (only mask if Luhn-valid)
        for match in _BANK_CARD_PATTERN._compiled.finditer(result):
            candidate = match.group()
            digits_only = re.sub(r"\D", "", candidate)
            if _luhn_check(digits_only):
                result = result.replace(
                    candidate, _BANK_CARD_PATTERN.replacement, 1
                )
                total_count += 1

        return result, total_count

    def mask_dict(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Recursively mask PII in a dictionary.

        Args:
            data: Input dictionary.

        Returns:
            Tuple of (masked_dict, total_replacements).
        """
        total_count = 0
        result: dict[str, Any] = {}

        for key, value in data.items():
            if isinstance(value, str):
                masked, count = self.mask_string(value)
                result[key] = masked
                total_count += count
            elif isinstance(value, dict):
                masked_dict, count = self.mask_dict(value)
                result[key] = masked_dict
                total_count += count
            elif isinstance(value, list):
                masked_list, count = self._mask_list(value)
                result[key] = masked_list
                total_count += count
            else:
                result[key] = value

        return result, total_count

    def _mask_list(self, items: list[Any]) -> tuple[list[Any], int]:
        """Recursively mask PII in a list."""
        total_count = 0
        result: list[Any] = []

        for item in items:
            if isinstance(item, str):
                masked, count = self.mask_string(item)
                result.append(masked)
                total_count += count
            elif isinstance(item, dict):
                masked_dict, count = self.mask_dict(item)
                result.append(masked_dict)
                total_count += count
            elif isinstance(item, list):
                masked_list, count = self._mask_list(item)
                result.append(masked_list)
                total_count += count
            else:
                result.append(item)

        return result, total_count

    def mask_response(
        self, response: ToolCallResponse
    ) -> ToolCallResponse:
        """Mask PII in a ToolCallResponse.

        Args:
            response: The tool call response.

        Returns:
            New response with PII masked in content.
        """
        masked_content: list[dict[str, Any]] = []
        for item in response.content:
            masked_item, _ = self.mask_dict(item)
            masked_content.append(masked_item)

        return response.model_copy(update={"content": masked_content})

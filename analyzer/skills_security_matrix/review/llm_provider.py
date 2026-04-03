from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ReviewRequest, ReviewResponse


class LLMReviewProvider(ABC):
    provider_name: str

    @abstractmethod
    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        raise NotImplementedError


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMReviewProvider] = {}

    def register(self, provider: LLMReviewProvider) -> None:
        self._providers[provider.provider_name] = provider

    def get(self, name: str | None) -> LLMReviewProvider | None:
        if not name:
            return None
        return self._providers.get(name)

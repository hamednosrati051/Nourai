"""Provider interfaces and result dataclasses.

Business code depends only on these abstractions, never on a specific
vendor's request/response shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# -- SMS -------------------------------------------------------------------
@dataclass
class SendOtpResult:
    ok: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    # Dev/test only: echoed code. Never set in production.
    dev_code: str | None = None


class SmsProvider(ABC):
    @abstractmethod
    def send_otp(self, mobile: str, code: str) -> SendOtpResult:
        ...


# -- Payments ----------------------------------------------------------------
@dataclass
class PaymentStart:
    track_id: str
    payment_url: str
    raw: dict = field(default_factory=dict)


@dataclass
class PaymentVerify:
    ok: bool
    paid: bool
    track_id: str | None = None
    gateway_reference: str | None = None
    amount_in_gateway_unit: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class PaymentGateway(ABC):
    @abstractmethod
    def create_payment(self, amount_irr: int, callback_url: str, metadata: dict) -> PaymentStart:
        ...

    @abstractmethod
    def verify_payment(self, track_id: str, amount_irr: int) -> PaymentVerify:
        ...


# -- AI -----------------------------------------------------------------------
@dataclass
class TextResult:
    ok: bool
    text: str = ""
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # "provider" when usage comes from the provider, else None (use tiktoken).
    usage_source: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class TranscriptResult:
    ok: bool
    text: str = ""
    provider_request_id: str | None = None
    duration_seconds: int | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class AudioResult:
    ok: bool
    audio_bytes: bytes = b""
    mime_type: str = "audio/mpeg"
    provider_request_id: str | None = None
    duration_seconds: int | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class ImageResult:
    ok: bool
    image_bytes: bytes = b""
    mime_type: str = "image/jpeg"
    width: int | None = None
    height: int | None = None
    provider_request_id: str | None = None
    revised_prompt: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    # Provider-reported generation cost in USD cents (when the API reports
    # it). Used for cost-plus-margin protection; None = unknown.
    provider_cost_cents: int | None = None


class TextAiProvider(ABC):
    @abstractmethod
    def generate(self, model: str, messages: list[dict], options: dict) -> TextResult:
        ...


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, model: str, audio_key: str, options: dict) -> TranscriptResult:
        ...


class TextToSpeechProvider(ABC):
    @abstractmethod
    def synthesize(self, model: str, text: str, options: dict) -> AudioResult:
        ...


class ImageAiProvider(ABC):
    @abstractmethod
    def generate(self, model: str, prompt: str, options: dict) -> ImageResult:
        ...

    @abstractmethod
    def edit(self, model: str, prompt: str, input_image_key: str, options: dict) -> ImageResult:
        ...


class ProviderError(Exception):
    """Normalized provider failure (safe to log, safe message for users)."""

    def __init__(self, code: str = "PROVIDER_ERROR", message: str = "provider failed"):
        super().__init__(message)
        self.code = code

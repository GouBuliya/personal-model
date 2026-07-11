"""HTTP model limits for paid Chat calls and trusted capture ingestion."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from persome.api.chat_models import MAX_CHAT_MESSAGE_CHARS, SendMessageRequest
from persome.api.models import (
    MAX_CAPTURE_AX_TREE_BYTES,
    MAX_CAPTURE_IMAGE_B64_CHARS,
    CaptureIngestBody,
)


def test_chat_message_has_a_hard_character_limit() -> None:
    with pytest.raises(ValidationError, match="String should have at most"):
        SendMessageRequest(content="x" * (MAX_CHAT_MESSAGE_CHARS + 1))


def test_chat_message_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="String should have at least"):
        SendMessageRequest(content="")


def test_capture_rejects_oversized_screenshot_before_ingest() -> None:
    with pytest.raises(ValidationError, match="screenshot.image_base64"):
        CaptureIngestBody(screenshot={"image_base64": "A" * (MAX_CAPTURE_IMAGE_B64_CHARS + 1)})


def test_capture_rejects_oversized_ocr_payload_before_decode() -> None:
    with pytest.raises(ValidationError, match="String should have at most"):
        CaptureIngestBody(ocr_jpeg_b64="A" * (MAX_CAPTURE_IMAGE_B64_CHARS + 1))


def test_capture_rejects_oversized_ax_tree() -> None:
    with pytest.raises(ValidationError, match="ax_tree exceeds"):
        CaptureIngestBody(ax_tree={"text": "x" * (MAX_CAPTURE_AX_TREE_BYTES + 1)})

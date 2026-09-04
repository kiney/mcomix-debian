"""Client for OpenAI-compatible vision and image-edit endpoints."""

import base64
import binascii
import io
from typing import Any, Dict
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

from mcomix.i18n import _


MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ERROR_TEXT = 1000


class AIError(Exception):
    """An error suitable for display to the user."""


def _headers(api_key: str) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    return headers


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error", payload)
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)[:MAX_ERROR_TEXT]
    except (ValueError, AttributeError):
        pass
    text = (response.text or response.reason or "").strip()
    return text[:MAX_ERROR_TEXT]


def _check_response(response: requests.Response) -> None:
    if not response.ok:
        message = _error_message(response)
        if message:
            raise AIError("HTTP %s: %s" % (response.status_code, message))
        raise AIError("HTTP %s" % response.status_code)


def _json(response: requests.Response) -> Dict[str, Any]:
    _check_response(response)
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise AIError(_("The API response is too large."))
    try:
        payload = response.json()
    except ValueError as error:
        raise AIError(_("The API returned invalid JSON.")) from error
    if not isinstance(payload, dict):
        raise AIError(_("The API returned an unexpected response."))
    return payload


def _request_error(error: requests.RequestException) -> AIError:
    if isinstance(error, requests.Timeout):
        return AIError(_("The API request timed out."))
    return AIError(_("The API request failed: %s") % error)


def ask_about_image(endpoint: str, api_key: str, model: str,
                    prompt: str, image_png: bytes, timeout: int) -> str:
    """Send a PNG and prompt to a Chat Completions compatible endpoint."""
    image_url = "data:image/png;base64,%s" % base64.b64encode(
        image_png).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": image_url,
                    "detail": "high",
                }},
            ],
        }],
    }
    try:
        response = requests.post(endpoint, headers=_headers(api_key),
                                 json=payload, timeout=(10, timeout))
    except requests.RequestException as error:
        raise _request_error(error) from error

    data = _json(response)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIError(_("The API response does not contain a text answer.")) from error

    if isinstance(content, str):
        answer = content
    elif isinstance(content, list):
        answer = "\n".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") in ("text", "output_text")
        )
    else:
        answer = ""
    if not answer.strip():
        raise AIError(_("The API response does not contain a text answer."))
    return answer.strip()


def _download_image(url: str, timeout: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise AIError(_("The API returned an unsupported image URL."))
    try:
        response = requests.get(url, stream=True, timeout=(10, timeout))
        _check_response(response)
        chunks = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise AIError(_("The returned image is too large."))
            chunks.append(chunk)
        return b"".join(chunks)
    except requests.RequestException as error:
        raise _request_error(error) from error


def _validate_image(image_data: bytes) -> bytes:
    if not image_data or len(image_data) > MAX_RESPONSE_BYTES:
        raise AIError(_("The returned image is empty or too large."))
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            image.load()
            if image.width < 1 or image.height < 1:
                raise AIError(_("The API returned an invalid image."))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise AIError(_("The API returned invalid image data.")) from error
    return image_data


def transform_image(endpoint: str, api_key: str, model: str,
                    prompt: str, image_png: bytes, timeout: int) -> bytes:
    """Send a PNG to an Images Edits compatible endpoint and return an image."""
    files = {"image": ("mcomix-page.png", image_png, "image/png")}
    form = {"model": model, "prompt": prompt}
    try:
        response = requests.post(endpoint, headers=_headers(api_key),
                                 data=form, files=files,
                                 timeout=(10, timeout))
    except requests.RequestException as error:
        raise _request_error(error) from error

    data = _json(response)
    try:
        result = data["data"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise AIError(_("The API response does not contain an image.")) from error

    if not isinstance(result, dict):
        raise AIError(_("The API response does not contain an image."))
    if result.get("b64_json"):
        try:
            image_data = base64.b64decode(result["b64_json"], validate=True)
        except (binascii.Error, ValueError, TypeError) as error:
            raise AIError(_("The API returned invalid base64 image data.")) from error
    elif result.get("url"):
        image_data = _download_image(result["url"], timeout)
    else:
        raise AIError(_("The API response does not contain an image."))
    return _validate_image(image_data)

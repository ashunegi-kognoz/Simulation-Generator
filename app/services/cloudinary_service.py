"""Cloudinary image hosting, using a signed REST upload (no SDK dependency).

Signing: alphabetically sort the params to sign, join as ``key=value`` with ``&``,
append the API secret, and take the SHA-1 hex digest. The upload accepts a base64
data URI as the ``file`` field, so the frontend can hand us the image as a data URL.
"""

from __future__ import annotations

import hashlib
import time

import httpx

from app.config import get_settings


class CloudinaryError(Exception):
    """Raised when Cloudinary is unconfigured or an API call fails."""


def _sign(params: dict[str, str], api_secret: str) -> str:
    to_sign = "&".join(
        f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, "")
    )
    return hashlib.sha1((to_sign + api_secret).encode()).hexdigest()


async def upload_image(*, data_uri: str, folder: str) -> dict:
    """Upload a base64 data URI to Cloudinary; returns url + public_id + metadata."""
    s = get_settings()
    if not s.cloudinary_configured:
        raise CloudinaryError("Cloudinary is not configured on the server.")
    timestamp = str(int(time.time()))
    signed = {"timestamp": timestamp, "folder": folder}
    signature = _sign(signed, s.cloudinary_api_secret)
    form = {
        **signed,
        "api_key": s.cloudinary_api_key,
        "signature": signature,
        "file": data_uri,
    }
    url = f"https://api.cloudinary.com/v1_1/{s.cloudinary_cloud_name}/image/upload"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, data=form)
    except httpx.HTTPError as exc:
        raise CloudinaryError(f"Could not reach Cloudinary: {exc}") from exc
    if resp.status_code >= 400:
        raise CloudinaryError(f"Cloudinary upload failed ({resp.status_code}): {resp.text[:300]}")
    body = resp.json()
    return {
        "url": body["secure_url"],
        "public_id": body["public_id"],
        "content_type": body.get("format", ""),
        "bytes": body.get("bytes"),
    }


async def delete_image(public_id: str) -> None:
    """Best-effort delete of a Cloudinary asset by public_id."""
    s = get_settings()
    if not s.cloudinary_configured or not public_id:
        return
    timestamp = str(int(time.time()))
    signed = {"public_id": public_id, "timestamp": timestamp}
    signature = _sign(signed, s.cloudinary_api_secret)
    form = {**signed, "api_key": s.cloudinary_api_key, "signature": signature}
    url = f"https://api.cloudinary.com/v1_1/{s.cloudinary_cloud_name}/image/destroy"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(url, data=form)
    except httpx.HTTPError:
        pass  # deletion is best-effort; the DB row is already gone

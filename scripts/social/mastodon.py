"""Mastodon-Posting über die REST-API. Kein Mastodon.py als Abhängigkeit -
ein POST mit Bearer-Token ist trivial genug für urllib."""

import json
import mimetypes
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class MastodonError(RuntimeError):
    pass


def verify_credentials(instance: str, access_token: str) -> dict:
    req = urllib.request.Request(
        f"{instance}/api/v1/accounts/verify_credentials",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MastodonError(f"Mastodon-Verifizierung fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc


def post_status(instance: str, access_token: str, text: str) -> dict:
    body = urllib.parse.urlencode({"status": text}).encode()
    req = urllib.request.Request(
        f"{instance}/api/v1/statuses",
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MastodonError(f"Mastodon-Post fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc
    return {"url": result.get("url"), "id": result.get("id")}


def update_credentials(
    instance: str,
    access_token: str,
    fields: dict | None = None,
    avatar_path: Path | None = None,
) -> dict:
    """PATCH /api/v1/accounts/update_credentials. Multipart nur, wenn ein
    Avatar/Header mitgeschickt wird - sonst reicht form-urlencoded."""
    fields = fields or {}
    if avatar_path is None:
        body = urllib.parse.urlencode(fields).encode()
        content_type = "application/x-www-form-urlencoded"
    else:
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in fields.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )
        mime = mimetypes.guess_type(avatar_path.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="avatar"; filename="{avatar_path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode()
            + avatar_path.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        content_type = f"multipart/form-data; boundary={boundary}"

    req = urllib.request.Request(
        f"{instance}/api/v1/accounts/update_credentials",
        data=body,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": content_type},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MastodonError(f"Profil-Update fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc

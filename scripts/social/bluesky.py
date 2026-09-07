"""Bluesky-Posting über AT-Protocol-Rohaufrufe. Kein atproto-SDK -
Login + createRecord sind zwei POSTs, das SDK wäre für einen einzelnen
Textpost unverhältnismässig viel Fläche."""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://bsky.social/xrpc"


class BlueskyError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise BlueskyError(f"Bluesky-Aufruf fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc


def create_session(handle: str, app_password: str) -> dict:
    return _post_json(f"{API}/com.atproto.server.createSession", {"identifier": handle, "password": app_password})


def create_app_password(access_jwt: str, name: str) -> dict:
    """Erzeugt ein neues App-Passwort für die eingeloggte Session - Bluesky
    erlaubt das regulär authentifiziert per API, nicht nur über die
    Einstellungen-Seite im Browser."""
    return _post_json(f"{API}/com.atproto.server.createAppPassword", {"name": name}, token=access_jwt)


def _link_facets(text: str) -> list[dict]:
    facets = []
    for match in re.finditer(r"https?://\S+", text):
        start_bytes = len(text[: match.start()].encode("utf-8"))
        end_bytes = len(text[: match.end()].encode("utf-8"))
        facets.append(
            {
                "index": {"byteStart": start_bytes, "byteEnd": end_bytes},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": match.group(0)}],
            }
        )
    return facets


def post(handle: str, app_password: str, text: str) -> dict:
    session = create_session(handle, app_password)
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    facets = _link_facets(text)
    if facets:
        record["facets"] = facets

    result = _post_json(
        f"{API}/com.atproto.repo.createRecord",
        {"repo": session["did"], "collection": "app.bsky.feed.post", "record": record},
        token=session["accessJwt"],
    )
    rkey = result["uri"].rsplit("/", 1)[-1]
    url = f"https://bsky.app/profile/{handle}/post/{rkey}"
    return {"url": url, "uri": result["uri"]}

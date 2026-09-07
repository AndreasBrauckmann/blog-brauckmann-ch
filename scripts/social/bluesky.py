"""Bluesky-Posting über AT-Protocol-Rohaufrufe. Kein atproto-SDK -
Login + createRecord sind zwei POSTs, das SDK wäre für einen einzelnen
Textpost unverhältnismässig viel Fläche."""

import json
import re
import urllib.error
import urllib.parse
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


def _get_json(url: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def upload_blob(access_jwt: str, data: bytes, mime_type: str) -> dict:
    req = urllib.request.Request(
        f"{API}/com.atproto.repo.uploadBlob",
        data=data,
        headers={"Content-Type": mime_type, "Authorization": f"Bearer {access_jwt}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["blob"]
    except urllib.error.HTTPError as exc:
        raise BlueskyError(f"Blob-Upload fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc


def update_profile(
    handle: str,
    app_password: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
    avatar: tuple[bytes, str] | None = None,
) -> dict:
    """Setzt Anzeigename/Beschreibung/Profilbild. putRecord ersetzt den
    kompletten Profil-Datensatz - deshalb wird der bestehende erst gelesen
    und nur gezielt ergänzt, damit ein vorhandenes Feld (z.B. ein Banner)
    nicht versehentlich verschwindet."""
    session = create_session(handle, app_password)
    did, token = session["did"], session["accessJwt"]

    try:
        existing = _get_json(
            f"{API}/com.atproto.repo.getRecord?"
            + urllib.parse.urlencode({"repo": did, "collection": "app.bsky.actor.profile", "rkey": "self"}),
            token=token,
        )
        record = existing["value"]
    except urllib.error.HTTPError:
        record = {"$type": "app.bsky.actor.profile"}

    if display_name is not None:
        record["displayName"] = display_name
    if description is not None:
        record["description"] = description
    if avatar is not None:
        data, mime_type = avatar
        record["avatar"] = upload_blob(token, data, mime_type)

    return _post_json(
        f"{API}/com.atproto.repo.putRecord",
        {"repo": did, "collection": "app.bsky.actor.profile", "rkey": "self", "record": record},
        token=token,
    )


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

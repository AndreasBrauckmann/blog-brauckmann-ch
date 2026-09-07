"""Mastodon-Posting über die REST-API. Kein Mastodon.py als Abhängigkeit -
ein POST mit Bearer-Token ist trivial genug für urllib."""

import json
import urllib.error
import urllib.parse
import urllib.request


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

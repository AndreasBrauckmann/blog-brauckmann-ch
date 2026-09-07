"""LinkedIn-Posting über die Self-Serve-API (Produkt "Share on LinkedIn",
Scope w_member_social). Kein SDK - zwei REST-Aufrufe pro Post."""

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.linkedin.com/v2"


class LinkedInError(RuntimeError):
    pass


def _request(method: str, url: str, access_token: str, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raise LinkedInError(f"LinkedIn-Aufruf fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc


def get_person_urn(access_token: str) -> str:
    """Erfordert die Scopes 'openid' und 'profile' (Produkt 'Sign In with
    LinkedIn using OpenID Connect'), zusätzlich zu 'w_member_social'."""
    info = _request("GET", f"{API}/userinfo", access_token)
    if "sub" not in info:
        raise LinkedInError(f"Kein 'sub' in /userinfo-Antwort: {info}")
    return f"urn:li:person:{info['sub']}"


def post_share(access_token: str, person_urn: str, text: str) -> dict:
    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        f"{API}/ugcPosts", data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            share_urn = resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id")
    except urllib.error.HTTPError as exc:
        raise LinkedInError(f"LinkedIn-Post fehlgeschlagen: {exc.code} {exc.read().decode()}") from exc
    return {"urn": share_urn, "url": f"https://www.linkedin.com/feed/update/{share_urn}/"}


def post_comment(access_token: str, actor_urn: str, share_urn: str, text: str) -> dict:
    payload = {"actor": actor_urn, "message": {"text": text}}
    encoded_urn = urllib.parse.quote(share_urn, safe="")
    return _request("POST", f"{API}/socialActions/{encoded_urn}/comments", access_token, payload)

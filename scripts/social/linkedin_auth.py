#!/usr/bin/env python3
"""Einmaliger OAuth-Flow für LinkedIn - erzeugt LINKEDIN_ACCESS_TOKEN.

Voraussetzung: LinkedIn-App im Developer Portal mit den Produkten
"Share on LinkedIn" und "Sign In with LinkedIn using OpenID Connect",
App über eine Company-Page verifiziert, Redirect-URI in der App exakt
identisch zu --redirect-uri hier eingetragen.

Nutzung:
    .venv/bin/python scripts/social/linkedin_auth.py \\
        --client-id ... --client-secret ... \\
        --redirect-uri http://<erreichbarer-host>:8765/callback

Der Token läuft nach ca. 60 Tagen ab und muss dann erneut so erzeugt werden.
"""

import argparse
import http.server
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
SCOPES = "openid profile w_member_social"

received: dict[str, str] = {}


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            received["code"] = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Autorisiert. Dieses Fenster kann geschlossen werden.".encode())
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Kein code-Parameter erhalten: {params}".encode())

    def log_message(self, format, *args):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--redirect-uri", required=True, help="Muss exakt der in der LinkedIn-App hinterlegten URI entsprechen")
    args = parser.parse_args()

    port = urllib.parse.urlparse(args.redirect_uri).port or 80
    server = http.server.HTTPServer(("0.0.0.0", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    auth_params = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "scope": SCOPES,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    print(f"Öffne diese URL in einem Browser, der {args.redirect_uri} erreichen kann:\n\n{url}\n")
    print("Warte auf Autorisierung (Timeout: 5 Minuten) ...")
    thread.join(timeout=300)

    if "code" not in received:
        print("FEHLER: kein Code erhalten (Timeout oder Abbruch).", file=sys.stderr)
        return 1

    token_params = {
        "grant_type": "authorization_code",
        "code": received["code"],
        "redirect_uri": args.redirect_uri,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
    }
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(token_params).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"FEHLER beim Token-Tausch: {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1

    print("\nErfolgreich. Trage das in .env ein:\n")
    print(f"LINKEDIN_ACCESS_TOKEN={token_data['access_token']}")
    print(f"\n(läuft ab in {token_data.get('expires_in', '?')} Sekunden)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

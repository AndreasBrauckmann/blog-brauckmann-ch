"""Quick-Redaktor: Seite für Kolleginnen und Kollegen (Blueprint im Prozess der Verwaltung, aber getrennt).

Erreichbar unter zwei Präfixen, dieselben Ansichten:
- /verwaltung/redaktor  über den bestehenden edge-Caddy (LAN/Tailnet), solange es keine Freigabe gibt
- /redaktor             für eine spätere Freigabe (Vorschlag: docs-intern/redaktor-freigabe.md; Caddy unverändert)

Grenzen: keine Artikeldaten, keine Verwaltungsfunktion, kein Link in die Verwaltung. Die Navigation der Verwaltung
wird nicht eingebunden (eigene Vorlagen unter templates/redaktor/). Der Betreiberhinweis erscheint nur, wenn die
Anfrage über den internen edge-Weg kam (Header X-Blog-Verwaltung-Intern), also nie bei einer Freigabe nach Vorschlag.

Schutz: gemeinsamer Zugangscode (REDAKTOR_CODE), signiertes Sitzungs-Cookie, CSRF-Token je Sitzung,
Ratenbegrenzung je IP und je Tag, Textlänge begrenzt. Texte werden weder gespeichert noch protokolliert.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from flask import Blueprint, abort, make_response, redirect, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

import plattformen as pf
import redaktor as rd

bp = Blueprint("redaktor", __name__, template_folder="templates")

COOKIE = "redaktor_sitzung"
SITZUNG_S = 12 * 3600
_PROZESS_SCHLUESSEL = secrets.token_hex(32)  # ohne REDAKTOR_SITZUNG_SCHLUESSEL gilt eine Sitzung bis zum Neustart

begrenzer = rd.Ratenbegrenzer()
zaehler = rd.Zaehler()


def _serializer() -> URLSafeTimedSerializer:
    geheim = os.environ.get("REDAKTOR_SITZUNG_SCHLUESSEL", "").strip() or _PROZESS_SCHLUESSEL
    return URLSafeTimedSerializer(geheim, salt="quick-redaktor")


def _code_kennung(code: str) -> str:
    """Kurzer Fingerabdruck des Codes: wechselt der Code, sind alle Sitzungen ungültig."""
    return hashlib.sha256(("redaktor:" + code).encode()).hexdigest()[:16]


def _basis() -> str:
    """/verwaltung/redaktor (interner Weg) oder /redaktor (Freigabe-Weg) - je nachdem, wie die Seite aufgerufen wurde."""
    return "/verwaltung/redaktor" if request.path.startswith("/verwaltung/") else "/redaktor"


def client_ip() -> str:
    """Die vom edge-Caddy angehängte Adresse (letzter Eintrag in X-Forwarded-For); wird nie gespeichert."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.remote_addr or "?"


def intern() -> bool:
    return bool(request.headers.get("X-Blog-Verwaltung-Intern"))


def sitzung() -> dict | None:
    code = rd.einstellungen()["code"]
    roh = request.cookies.get(COOKIE)
    if not code or not roh:
        return None
    try:
        d = _serializer().loads(roh, max_age=SITZUNG_S)
    except BadSignature:
        return None
    if not isinstance(d, dict) or not hmac.compare_digest(str(d.get("k", "")), _code_kennung(code)):
        return None
    return d


def _seite(vorlage: str, status: int = 200, **kw):
    e = rd.einstellungen()
    ok, warum = rd.llm_verfuegbar()
    kontext = dict(basis=_basis(), intern=intern(), llm_an=ok, llm_hinweis=warum, llm_modus=e["llm_modus"], max_zeichen=e["max_zeichen"],
                   limit_stunde=e["limit_stunde_ip"], limit_tag=e["limit_tag"], modi=rd.MODI, ziele=rd.ZIELE,
                   code_fehlt=not e["code"], sichtbar_mobil=pf.LINKEDIN_SICHTBAR_MOBIL, sichtbar_desktop=pf.LINKEDIN_SICHTBAR_DESKTOP,
                   karte_max=pf.LINKEDIN_KARTE_MAX)
    kontext.update(kw)
    antwort = make_response(render_template(vorlage, **kontext), status)
    antwort.headers["Cache-Control"] = "no-store"
    antwort.headers["X-Robots-Tag"] = "noindex, nofollow"
    antwort.headers["Referrer-Policy"] = "no-referrer"
    return antwort


def _csrf_pruefen(s: dict) -> None:
    if not hmac.compare_digest(str(s.get("csrf", "")), request.form.get("csrf", "")):
        abort(403, "Formular-Token ungültig. Seite neu laden und erneut versuchen.")


@bp.route("/redaktor", methods=["GET"])
@bp.route("/redaktor/", methods=["GET"])
def start():
    s = sitzung()
    if not s:
        return _seite("redaktor/anmelden.html")
    return _seite("redaktor/redaktor.html", csrf=s["csrf"], eingabe="", modus="behutsam" if rd.llm_verfuegbar()[0] else "pruefen",
                  ziel=600, aufbau=False)


@bp.route("/redaktor/anmelden", methods=["POST"])
def anmelden():
    code = rd.einstellungen()["code"]
    if not code:
        return _seite("redaktor/anmelden.html", 503, fehler="Der Zugang ist noch nicht eingerichtet.")
    ip = client_ip()
    eingabe = request.form.get("code", "")
    # Fehlversuche zählen nur bei falschem Code; nach zu vielen ist für eine Stunde Schluss
    if _gesperrt(ip):
        return _seite("redaktor/anmelden.html", 429, fehler="Zu viele Fehlversuche. Bitte in einer Stunde erneut versuchen.")
    if not hmac.compare_digest(eingabe.strip().encode(), code.encode()):
        _fehlversuch(ip)
        return _seite("redaktor/anmelden.html", 403, fehler="Der Zugangscode stimmt nicht.")
    wert = _serializer().dumps({"k": _code_kennung(code), "csrf": secrets.token_urlsafe(24)})
    antwort = redirect(_basis() + "/")
    sicher = request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https"
    antwort.set_cookie(COOKIE, wert, max_age=SITZUNG_S, httponly=True, samesite="Strict", secure=sicher, path=_basis())
    return antwort


fehlversuche = rd.Ratenbegrenzer()


def _gesperrt(ip: str) -> bool:
    return fehlversuche.anzahl(ip) >= rd.einstellungen()["fehlversuche_stunde"]


def _fehlversuch(ip: str) -> None:
    fehlversuche.zulassen(ip, 10 ** 6)


@bp.route("/redaktor/abmelden", methods=["POST"])
def abmelden():
    s = sitzung()
    if s:
        _csrf_pruefen(s)
    antwort = redirect(_basis() + "/")
    antwort.delete_cookie(COOKIE, path=_basis())
    return antwort


@bp.route("/redaktor/pruefen", methods=["POST"])
def pruefen():
    s = sitzung()
    if not s:
        return redirect(_basis() + "/")
    _csrf_pruefen(s)
    e = rd.einstellungen()
    text = request.form.get("text", "")
    modus = request.form.get("modus", "pruefen")
    try:
        ziel = int(request.form.get("ziel", "600"))
    except ValueError:
        ziel = 600
    aufbau = request.form.get("aufbau") == "ja"
    formular = dict(csrf=s["csrf"], eingabe=text, modus=modus, ziel=ziel, aufbau=aufbau)
    if not text.strip():
        return _seite("redaktor/redaktor.html", 400, fehler="Bitte zuerst einen Beitragstext einfügen.", **formular)
    if len(text) > e["max_zeichen"]:
        return _seite("redaktor/redaktor.html", 413, fehler=f"Der Text hat {len(text)} Zeichen. Erlaubt sind höchstens {e['max_zeichen']}.", **formular)
    if zaehler.heute() >= e["limit_tag"]:
        return _seite("redaktor/redaktor.html", 429, fehler="Das Tageskontingent ist aufgebraucht. Morgen geht es weiter.", **formular)
    if not begrenzer.zulassen(client_ip(), e["limit_stunde_ip"]):
        return _seite("redaktor/redaktor.html", 429, fehler=f"Höchstens {e['limit_stunde_ip']} Durchläufe je Stunde. Bitte etwas später erneut versuchen.", **formular)
    try:
        erg = rd.verarbeite(text, modus, ziel=ziel, aufbau_erlaubt=aufbau)
    except rd.Belegt as exc:
        return _seite("redaktor/redaktor.html", 503, fehler=str(exc), **formular)
    zaehler.buchen({"laenge": len(text), "modus": erg["modus"], "dauer_s": erg["dauer_s"], "modell": erg["modell"],
                    "punkte_vorher": erg["vorher"]["punkte"], "punkte_nachher": (erg["nachher"] or erg["vorher"])["punkte"],
                    "aufrufe_llm": erg["aufrufe"], "ergebnis": "meldung" if erg["meldung"] else "ok"})
    formular["modus"] = erg["modus"]
    return _seite("redaktor/redaktor.html", erg=erg, **formular)

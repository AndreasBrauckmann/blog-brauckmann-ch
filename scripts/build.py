#!/usr/bin/env python3
"""Baut dist/ aus articles/*.md, templates/ und static/.

Nutzung:
    .venv/bin/python scripts/build.py [--help]
"""

import argparse
import html
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

import markdown
import yaml
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_template(name: str) -> str:
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def render(template: str, context: dict) -> str:
    out = template
    for key, value in context.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def parse_article(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path}: fehlendes YAML-Frontmatter")
    _, fm_raw, body = raw.split("---", 2)
    meta = yaml.safe_load(fm_raw) or {}
    required = ["title", "slug", "date", "description"]
    missing = [k for k in required if k not in meta]
    if missing:
        raise ValueError(f"{path}: Frontmatter fehlt Felder {missing}")
    meta["body_md"] = body.strip()
    meta["source"] = path
    return meta


def render_markdown(body_md: str) -> str:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "footnotes", "toc", "attr_list"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )
    return md.convert(body_md)


def build_jsonld(meta: dict, cfg: dict, canonical_url: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": meta["title"],
        "description": meta["description"],
        "datePublished": str(meta["date"]),
        "dateModified": str(meta.get("updated", meta["date"])),
        "author": {"@type": "Person", "name": cfg["site"]["author"]},
        "url": canonical_url,
    }
    if meta.get("image"):
        data["image"] = cfg["site"]["base_url"] + meta["image"]
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_article(meta: dict, cfg: dict, template: str, style: str, pygments_style: str) -> tuple[str, str]:
    site = cfg["site"]
    canonical_url = f"{site['base_url']}/artikel/{meta['slug']}/"
    content_html = render_markdown(meta["body_md"])
    tags = meta.get("tags", [])
    tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)
    og_image = site["base_url"] + meta["image"] if meta.get("image") else ""

    context = {
        "language": site["language"],
        "title": html.escape(meta["title"]),
        "site_title": html.escape(site["title"]),
        "description": html.escape(meta["description"]),
        "canonical_url": canonical_url,
        "og_image": og_image,
        "jsonld": build_jsonld(meta, cfg, canonical_url),
        "style": style,
        "pygments_style": pygments_style,
        "date_iso": str(meta["date"]),
        "date_display": str(meta["date"]),
        "tags_html": tags_html,
        "content": wrap_tables(content_html),
        "base_url": site["base_url"],
        "author": html.escape(site["author"]),
    }
    return meta["slug"], render(template, context)


def wrap_tables(content_html: str) -> str:
    return content_html.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )


def build_index(articles: list[dict], cfg: dict, template: str, style: str) -> str:
    site = cfg["site"]
    items = []
    for meta in articles:
        url = f"/artikel/{meta['slug']}/"
        tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in meta.get("tags", []))
        items.append(
            f'<div class="article-list-item">'
            f'<h2><a href="{url}">{html.escape(meta["title"])}</a></h2>'
            f'<time class="article-date" datetime="{meta["date"]}">{meta["date"]}</time>'
            f'<div class="tags">{tags_html}</div>'
            f'<p class="teaser">{html.escape(meta["description"])}</p>'
            f"</div>"
        )
    context = {
        "language": site["language"],
        "site_title": html.escape(site["title"]),
        "description": html.escape(site["description"]),
        "base_url": site["base_url"],
        "style": style,
        "article_list_html": "\n".join(items),
        "author": html.escape(site["author"]),
    }
    return render(template, context)


def build_sitemap(articles: list[dict], cfg: dict) -> str:
    base = cfg["site"]["base_url"]
    urls = [f"{base}/"] + [f"{base}/artikel/{m['slug']}/" for m in articles]
    body = "\n".join(f"  <url><loc>{xml_escape(u)}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def build_rss(articles: list[dict], cfg: dict) -> str:
    site = cfg["site"]
    items = []
    for meta in articles[:20]:
        url = f"{site['base_url']}/artikel/{meta['slug']}/"
        pub_date = datetime.strptime(str(meta["date"]), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        items.append(
            "  <item>\n"
            f"    <title>{xml_escape(meta['title'])}</title>\n"
            f"    <link>{xml_escape(url)}</link>\n"
            f"    <guid>{xml_escape(url)}</guid>\n"
            f"    <description>{xml_escape(meta['description'])}</description>\n"
            f"    <pubDate>{pub_date.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>\n"
            "  </item>"
        )
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"  <title>{xml_escape(site['title'])}</title>\n"
        f"  <link>{xml_escape(site['base_url'])}</link>\n"
        f"  <description>{xml_escape(site['description'])}</description>\n"
        f"{body}\n"
        "</channel></rss>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    cfg = load_config()
    articles_dir = ROOT / cfg["paths"]["articles_dir"]
    dist_dir = ROOT / cfg["paths"]["dist_dir"]
    static_dir = ROOT / cfg["paths"]["static_dir"]

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    style = (static_dir / "style.css").read_text(encoding="utf-8")
    pygments_style = HtmlFormatter().get_style_defs(".codehilite")

    md_files = sorted(p for p in articles_dir.glob("*.md") if p.is_file())
    articles = []
    for path in md_files:
        try:
            meta = parse_article(path)
        except ValueError as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            return 1
        if meta.get("draft", False):
            continue
        articles.append(meta)

    articles.sort(key=lambda m: str(m["date"]), reverse=True)

    article_template = load_template("article.html")
    index_template = load_template("index.html")

    for meta in articles:
        slug, page_html = build_article(meta, cfg, article_template, style, pygments_style)
        out_dir = dist_dir / "artikel" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(page_html, encoding="utf-8")

    (dist_dir / "index.html").write_text(
        build_index(articles, cfg, index_template, style), encoding="utf-8"
    )
    (dist_dir / "sitemap.xml").write_text(build_sitemap(articles, cfg), encoding="utf-8")
    (dist_dir / "rss.xml").write_text(build_rss(articles, cfg), encoding="utf-8")
    (dist_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {cfg['site']['base_url']}/sitemap.xml\n",
        encoding="utf-8",
    )

    if static_dir.exists():
        shutil.copytree(static_dir, dist_dir / "static", dirs_exist_ok=True)

    hostname = urlparse(cfg["site"]["base_url"]).hostname
    if hostname:
        (dist_dir / "CNAME").write_text(hostname + "\n", encoding="utf-8")

    public_root_dir = ROOT / "public-root"
    if public_root_dir.exists():
        shutil.copytree(public_root_dir, dist_dir, dirs_exist_ok=True)

    print(f"Gebaut: {len(articles)} Artikel -> {dist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

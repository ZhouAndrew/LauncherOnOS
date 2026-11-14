#!/usr/bin/env python3
"""Import a Journal Two HTML or SiYuan Markdown ZIP export as a WordPress draft."""

import argparse
import base64
import getpass
import html
import json
import mimetypes
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


MEDIA_ATTRIBUTE = re.compile(r'(?P<attr>\b(?:src|href))="(?P<url>[^"]*)"')


def read_document(archive, selected=None):
    if not selected and "note.html" in archive.namelist():
        document = archive.read("note.html").decode("utf-8")
        title = re.search(r"<title>(.*?)</title>", document, re.S)
        body = re.search(r"<body>(.*?)</body>", document, re.S)
        if not title or not body:
            raise ValueError("Expected a Journal Two HTML export")
        return "note.html", html.unescape(title.group(1)) or "Journal Two", body.group(1).strip()

    documents = [entry for entry in archive.namelist()
                 if entry.lower().endswith(".md") and "assets" not in PurePosixPath(entry).parts
                 and "__MACOSX" not in PurePosixPath(entry).parts]
    if selected is None and len(documents) == 1:
        selected = documents[0]
    if selected not in documents:
        raise ValueError("Select one Markdown document with --document. Available: " + ", ".join(documents))
    try:
        import bleach
        from markdown_it import MarkdownIt
    except ImportError as error:
        raise ValueError("Install Markdown dependencies with pip install markdown-it-py bleach") from error
    markdown = archive.read(selected).decode("utf-8-sig")
    rendered = MarkdownIt("commonmark", {"html": True}).enable("table").render(markdown)
    body = bleach.clean(
        rendered,
        tags=set(bleach.ALLOWED_TAGS) | {
            "p", "img", "video", "audio", "source", "figure", "figcaption", "div", "span",
            "h1", "h2", "h3", "h4", "h5", "h6", "pre", "hr", "br",
            "table", "thead", "tbody", "tr", "th", "td", "del", "input",
        },
        attributes={
            "a": ["href", "title"], "img": ["src", "alt", "title", "width", "height"],
            "video": ["src", "controls", "width", "height"], "audio": ["src", "controls"],
            "source": ["src", "type"], "input": ["type", "checked", "disabled"],
        },
        strip=True,
    )
    return selected, PurePosixPath(selected).stem, body


def asset_path(document, reference):
    url = urlsplit(html.unescape(reference))
    if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(url.path)))
    parts = PurePosixPath(path).parts
    if parts and parts[0] != ".." and ("assets" in parts or parts[0] == "attachments"):
        return path
    return None


def import_note(package, site, username, password, document=None):
    url = urlsplit(site)
    if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
        raise ValueError("Use the final HTTPS WordPress site URL")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    opener = build_opener(NoRedirect())

    def request(route, payload=None, headers=None):
        if headers is None:
            headers = {"Content-Type": "application/json"}
            if payload is not None:
                payload = json.dumps(payload).encode()
        req = Request(site.rstrip("/") + "/wp-json/wp/v2/" + route, data=payload,
                      headers={**headers, "Authorization": "Basic " + token})
        with opener.open(req, timeout=120) as response:
            return json.load(response)

    with ZipFile(package) as archive:
        document, title, content = read_document(archive, document)
        paths = {}
        for match in MEDIA_ATTRIBUTE.finditer(content):
            reference = match.group("url")
            path = asset_path(document, reference)
            if path is not None:
                archive.getinfo(path)
                paths[reference] = path
        draft = request("posts", {"title": title, "status": "draft"})
        post_id = int(draft["id"])
        print(f"Created draft {post_id}", flush=True)
        media_urls = {}
        for path in dict.fromkeys(paths.values()):
            name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(path).name)
            with archive.open(path) as attachment:
                media = request(f"media?post={post_id}", attachment, {
                    "Content-Disposition": f'attachment; filename="{name}"',
                    "Content-Type": mimetypes.guess_type(name)[0] or "application/octet-stream",
                    "Content-Length": str(archive.getinfo(path).file_size),
                })
            media_urls[path] = html.escape(media["source_url"], quote=True)

        def link(match):
            path = paths.get(match.group("url"))
            if path is None:
                return match.group()
            return f'{match.group("attr")}="{media_urls[path]}"'

        content = MEDIA_ATTRIBUTE.sub(link, content)
        request(f"posts/{post_id}", {"content": content, "status": "draft"})
        saved = request(f"posts/{post_id}?context=edit")
        if saved.get("status") != "draft" or saved.get("content", {}).get("raw") != content:
            raise ValueError(f"Draft {post_id} did not match the exported content after saving")
        return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("site")
    parser.add_argument("username")
    parser.add_argument("--document", help="Markdown path inside a multi-document ZIP")
    args = parser.parse_args()
    try:
        draft = import_note(args.package, args.site, args.username,
                            getpass.getpass("WordPress application password: "), args.document)
    except (HTTPError, OSError, ValueError, KeyError, BadZipFile) as error:
        parser.exit(1, f"Import failed: {error}\n")
    print(f"Draft saved: {args.site.rstrip('/')}/wp-admin/post.php?post={draft['id']}&action=edit")

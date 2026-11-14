#!/usr/bin/env python3
"""Import a Journal Two HTML export as a WordPress draft."""

import argparse
import base64
import getpass
import html
import json
import mimetypes
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def import_note(package, site, username, password):
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
        document = archive.read("note.html").decode("utf-8")
        title = re.search(r"<title>(.*?)</title>", document, re.S)
        body = re.search(r"<body>(.*?)</body>", document, re.S)
        if not title or not body:
            raise ValueError("Expected a Journal Two HTML export")
        content = body.group(1).strip()
        paths = set(re.findall(r'(?:src|href)="(attachments/[0-9]+(?:\.[A-Za-z0-9]{1,12})?)"', content))
        for path in paths:
            archive.getinfo(path)
        draft = request("posts", {"title": html.unescape(title.group(1)) or "Journal Two",
                                  "status": "draft"})
        post_id = int(draft["id"])
        print(f"Created draft {post_id}", flush=True)
        media_urls = {}
        for path in sorted(paths):
            name = Path(path).name
            with archive.open(path) as attachment:
                media = request(f"media?post={post_id}", attachment, {
                    "Content-Disposition": f'attachment; filename="{name}"',
                    "Content-Type": mimetypes.guess_type(name)[0] or "application/octet-stream",
                    "Content-Length": str(archive.getinfo(path).file_size),
                })
            media_urls[path] = html.escape(media["source_url"], quote=True)

        def link(match):
            attribute, path = match.groups()
            return f'{attribute}="{media_urls.get(path, path)}"'

        content = re.sub(r'\b(src|href)="(attachments/[0-9]+(?:\.[A-Za-z0-9]{1,12})?)"', link, content)
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
    args = parser.parse_args()
    try:
        draft = import_note(args.package, args.site, args.username,
                            getpass.getpass("WordPress application password: "))
    except (HTTPError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Import failed: {error}\n")
    print(f"Draft saved: {args.site.rstrip('/')}/wp-admin/post.php?post={draft['id']}&action=edit")

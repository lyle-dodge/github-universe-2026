#!/usr/bin/env python3
"""Print a reviewable Markdown session entry from an official Universe page."""

import argparse
from html.parser import HTMLParser
import json
import re
import sys
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


def validate_url(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in {
            "githubuniverse.com", "www.githubuniverse.com", "reg.githubuniverse.com"
        }
        or parts.username is not None
        or parts.password is not None
        or parts.port not in {None, 443}
    ):
        raise ValueError("Use an HTTPS session URL on an official Universe host.")
    return url


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = []
        self.events = []
        self.in_title = False
        self.json_parts = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name") or ""
            self.meta[key.lower()] = attrs.get("content") or ""
        elif tag == "title":
            self.in_title = True
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.json_parts = []

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.json_parts is not None:
            self.json_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.json_parts is not None:
            try:
                self.find_events(json.loads("".join(self.json_parts)))
            except json.JSONDecodeError:
                pass
            self.json_parts = None

    def find_events(self, value):
        if isinstance(value, list):
            for item in value:
                self.find_events(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if isinstance(types, list) and any(
                isinstance(kind, str) and kind.rsplit("/", 1)[-1].endswith("Event")
                for kind in types
            ):
                self.events.append(value)
            for item in value.values():
                if isinstance(item, (dict, list)):
                    self.find_events(item)


def text(value):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", value)


def session_markdown(html, url):
    validate_url(url)
    parser = MetadataParser()
    parser.feed(html)
    event = next((item for item in parser.events if item.get("name")), {})
    title = text(event.get("name")) or text(parser.meta.get("og:title"))
    title = title or text("".join(parser.title))
    if not title:
        raise ValueError("No session title found; review the official page manually.")
    description = text(event.get("description"))
    description = description or text(parser.meta.get("og:description"))
    description = description or text(parser.meta.get("description"))
    speakers = event.get("performer") or event.get("speaker") or []
    if not isinstance(speakers, list):
        speakers = [speakers]
    names = [text(item.get("name") if isinstance(item, dict) else item) for item in speakers]
    schedule = " – ".join(
        value for value in (text(event.get("startDate")), text(event.get("endDate"))) if value
    )
    link = quote(url, safe=":/?=&%#@+;,$-_.~")
    return (
        f"### {title}\n\n"
        f"- Official session: [{title}]({link})\n"
        f"- Speakers: {', '.join(name for name in names if name) or 'Not provided'}\n"
        f"- Schedule: {schedule or 'Not provided'}\n"
        f"- Summary: {description or 'Not provided'}\n"
        "- GitHub YouTube recording: **Pending verification**\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Individual HTTPS session URL on an official Universe host")
    args = parser.parse_args()
    try:
        url = validate_url(args.url)
        request = Request(url, headers={"User-Agent": "UniverseSessionCollector/1.0"})
        with build_opener(OfficialRedirects()).open(request, timeout=20) as response:
            html = response.read(2_000_001)
            if len(html) > 2_000_000:
                raise ValueError("Session page exceeds the 2 MB download limit.")
            html = html.decode(response.headers.get_content_charset() or "utf-8")
        print(session_markdown(html, url))
    except (URLError, ValueError, UnicodeError, OSError) as exc:
        print(f"Cannot scrape session: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

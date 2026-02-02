from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCES_DIR = Path(__file__).resolve().parent / "sources"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
DEFAULT_TIMEOUT = 10


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self.parts)


@dataclass
class KnowledgeSource:
    name: str
    url: str
    tags: list[str]
    key_points: list[str]


def _strip_html(content: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(content)
    return parser.get_text()


def _fetch_remote(url: str) -> str:
    request = Request(
        url,
        headers={"User-Agent": "GameDevKing/1.0 (+https://example.local)"},
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        return response.read().decode("utf-8", errors="ignore")


def _fetch_local(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _resolve_local_path(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        return None
    if parsed.scheme == "file":
        local = unquote(parsed.path).lstrip("/")
        return Path(local)
    path = Path(url)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _summarize(text: str, keywords: Iterable[str], limit: int = 8) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    key_points: list[str] = []
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) < 40 or len(cleaned) > 220:
            continue
        if any(word in cleaned.lower() for word in keywords):
            key_points.append(cleaned)
        if len(key_points) >= limit:
            break
    return key_points


def _read_sources(agent_name: str) -> list[dict]:
    path = SOURCES_DIR / f"{agent_name}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def _load_cache(agent_name: str) -> dict:
    path = CACHE_DIR / f"{agent_name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_cache(agent_name: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{agent_name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_knowledge(agent_name: str, keywords: Iterable[str]) -> list[KnowledgeSource]:
    sources = _read_sources(agent_name)
    if not sources:
        return []

    cache = _load_cache(agent_name)
    cached_sources = {entry.get("url"): entry for entry in cache.get("sources", [])}

    results: list[KnowledgeSource] = []
    for source in sources:
        url = source.get("url", "")
        cached = cached_sources.get(url)
        if cached:
            results.append(
                KnowledgeSource(
                    name=cached.get("name", source.get("name", "Source")),
                    url=url,
                    tags=cached.get("tags", source.get("tags", [])),
                    key_points=cached.get("key_points", []),
                )
            )
            continue

        try:
            local_path = _resolve_local_path(url)
            if local_path:
                content = _fetch_local(local_path)
            else:
                content = _fetch_remote(url)
            text = _strip_html(content) if "<html" in content.lower() else content
            key_points = _summarize(text, keywords=keywords)
        except Exception:
            key_points = []

        results.append(
            KnowledgeSource(
                name=source.get("name", "Source"),
                url=url,
                tags=source.get("tags", []),
                key_points=key_points,
            )
        )

    cache_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sources": [
            {
                "name": item.name,
                "url": item.url,
                "tags": item.tags,
                "key_points": item.key_points,
            }
            for item in results
        ],
    }
    _save_cache(agent_name, cache_payload)
    return results


def get_key_points(agent_name: str, keywords: Iterable[str], limit: int = 6) -> list[str]:
    knowledge = build_knowledge(agent_name, keywords)
    points: list[str] = []
    for source in knowledge:
        points.extend(source.key_points)
    return points[:limit]

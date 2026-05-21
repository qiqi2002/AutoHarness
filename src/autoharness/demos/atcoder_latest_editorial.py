"""Live WebWalk demo: find the latest finished AtCoder contest editorial."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any

from autoharness.demos.io import emit_result
from autoharness.llm import ChatClient, ChatConfig
from autoharness.webwalk import WebLink, WebPage, WebWalkLimits, WebWalkTool


ARCHIVE_URL = "https://atcoder.jp/contests/archive?lang=en"
RESULT_SCHEMA = "schemas/tasks/atcoder_latest_editorial.schema.json"


@dataclass(frozen=True)
class ContestCandidate:
    contest_id: str
    title: str
    url: str


def run_live_demo(*, use_model: bool = True) -> dict[str, Any]:
    walker = WebWalkTool(
        allowed_domains=["atcoder.jp"],
        limits=WebWalkLimits(max_pages=4, request_delay_ms=1000, timeout_seconds=30),
    )
    archive_page = walker.open(ARCHIVE_URL)
    contest = find_latest_finished_contest(archive_page)
    editorial_page = walker.open(f"{contest.url.rstrip('/')}/editorial")
    editorial_links = find_editorial_links(editorial_page, contest.contest_id)

    fallback = build_result(contest, editorial_page, editorial_links, walker.trace())
    if not use_model:
        return fallback

    model_result = ask_model_to_structure(contest, archive_page, editorial_page, editorial_links)
    return merge_with_fallback(model_result, fallback)


def find_latest_finished_contest(page: WebPage) -> ContestCandidate:
    seen: set[str] = set()
    for link in page.links:
        match = re.search(r"/contests/([a-z0-9_]+)$", link.url)
        if not match:
            continue
        contest_id = match.group(1)
        if contest_id in {"archive", "contests"} or contest_id in seen:
            continue
        seen.add(contest_id)
        return ContestCandidate(
            contest_id=contest_id,
            title=link.text,
            url=f"https://atcoder.jp/contests/{contest_id}",
        )
    raise ValueError("could not find a contest link in AtCoder archive")


def find_editorial_links(page: WebPage, contest_id: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in page.links:
        if f"/contests/{contest_id}/editorial/" not in link.url:
            continue
        if link.url in seen:
            continue
        seen.add(link.url)
        links.append(
            {
                "title": link.text,
                "editorial_url": link.url,
            }
        )
    return links


def build_result(
    contest: ContestCandidate,
    editorial_page: WebPage,
    editorial_links: list[dict[str, str]],
    trace: list[dict[str, str | int]],
) -> dict[str, Any]:
    return {
        "contest_id": contest.contest_id,
        "contest_title": contest.title,
        "contest_url": contest.url,
        "editorial_url": editorial_page.url,
        "problems": editorial_links,
        "evidence": [
            {
                "url": ARCHIVE_URL,
                "reason": "AtCoder contest archive was used as the source for the latest finished contest candidate.",
            },
            {
                "url": editorial_page.url,
                "reason": "Contest editorial page was opened directly under the selected contest.",
            },
        ],
        "webwalk_trace": trace,
    }


def ask_model_to_structure(
    contest: ContestCandidate,
    archive_page: WebPage,
    editorial_page: WebPage,
    editorial_links: list[dict[str, str]],
) -> dict[str, Any]:
    client = ChatClient(ChatConfig.from_env())
    return client.complete_json(
        [
            {
                "role": "system",
                "content": (
                    "You extract structured JSON for a web navigation task. "
                    "Return only one JSON object. Do not include markdown."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Return the latest finished AtCoder contest editorial information.",
                        "selected_contest": contest.__dict__,
                        "archive_context": compact_page(archive_page, max_links=20),
                        "editorial_context": compact_page(editorial_page, max_links=80),
                        "detected_editorial_links": editorial_links,
                        "required_shape": {
                            "contest_id": "string",
                            "contest_title": "string",
                            "contest_url": "string",
                            "editorial_url": "string",
                            "problems": [
                                {
                                    "title": "string",
                                    "editorial_url": "string",
                                }
                            ],
                            "evidence": [
                                {
                                    "url": "string",
                                    "reason": "string",
                                }
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )


def compact_page(page: WebPage, *, max_links: int) -> dict[str, Any]:
    return {
        "url": page.url,
        "title": page.title,
        "text_excerpt": page.text[:3000],
        "links": [link_to_dict(link) for link in page.links[:max_links]],
    }


def link_to_dict(link: WebLink) -> dict[str, str | int]:
    return {
        "id": link.id,
        "text": link.text,
        "url": link.url,
    }


def merge_with_fallback(model_result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    result = dict(fallback)
    for key in ["contest_id", "contest_title", "contest_url", "editorial_url", "problems", "evidence"]:
        value = model_result.get(key)
        if value:
            result[key] = value
    result["webwalk_trace"] = fallback["webwalk_trace"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find the latest AtCoder editorial via WebWalk.")
    parser.add_argument("--no-model", action="store_true", help="Run WebWalk extraction without calling the model.")
    parser.add_argument("--output", help="Optional path to write the JSON result.")
    parser.add_argument("--validate-schema", action="store_true", help="Validate output against the task schema.")
    args = parser.parse_args(argv)

    result = run_live_demo(use_model=not args.no_model)
    emit_result(
        result,
        output=args.output,
        schema_path=RESULT_SCHEMA if args.validate_schema else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

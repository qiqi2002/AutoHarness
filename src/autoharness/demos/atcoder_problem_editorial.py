"""Live WebWalk demo: find a specific AtCoder problem editorial."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

from autoharness.demos.atcoder_latest_editorial import compact_page, link_to_dict, merge_with_fallback
from autoharness.llm import ChatClient, ChatConfig
from autoharness.webwalk import WebLink, WebPage, WebWalkLimits, WebWalkTool


@dataclass(frozen=True)
class ProblemRequest:
    contest_id: str
    problem_id: str

    @property
    def problem_url(self) -> str:
        return f"https://atcoder.jp/contests/{self.contest_id}/tasks/{self.problem_id}"

    @property
    def editorial_index_url(self) -> str:
        return f"https://atcoder.jp/contests/{self.contest_id}/editorial"


@dataclass(frozen=True)
class EditorialCandidate:
    title: str
    url: str
    strategy: str


def run_live_demo(contest_id: str, problem_id: str, *, use_model: bool = True) -> dict[str, Any]:
    request = ProblemRequest(contest_id=contest_id, problem_id=problem_id)
    walker = WebWalkTool(
        allowed_domains=["atcoder.jp"],
        limits=WebWalkLimits(max_pages=5, request_delay_ms=1000, timeout_seconds=30),
    )

    problem_page = walker.open(request.problem_url)
    problem_title = extract_problem_title(problem_page, problem_id)
    editorial_index_page = walker.open(request.editorial_index_url)
    candidate = select_editorial_candidate(
        editorial_index_page,
        contest_id=contest_id,
        problem_id=problem_id,
        problem_title=problem_title,
    )
    editorial_page = walker.open(candidate.url)

    fallback = build_result(
        request=request,
        problem_title=problem_title,
        candidate=candidate,
        problem_page=problem_page,
        editorial_index_page=editorial_index_page,
        editorial_page=editorial_page,
        trace=walker.trace(),
    )
    if not use_model:
        return fallback

    model_result = ask_model_to_structure(
        request=request,
        problem_title=problem_title,
        candidate=candidate,
        problem_page=problem_page,
        editorial_index_page=editorial_index_page,
        editorial_page=editorial_page,
    )
    return merge_with_fallback(model_result, fallback)


def extract_problem_title(page: WebPage, problem_id: str) -> str:
    title = page.title
    if " - AtCoder" in title:
        title = title.split(" - AtCoder", 1)[0]
    if title:
        return title

    letter = problem_letter(problem_id)
    match = re.search(rf"\b{re.escape(letter)}\s*[-.]\s*[^|]+", page.text)
    if match:
        return match.group(0).strip()
    return problem_id


def select_editorial_candidate(
    page: WebPage,
    *,
    contest_id: str,
    problem_id: str,
    problem_title: str,
) -> EditorialCandidate:
    links = editorial_links(page, contest_id)
    if not links:
        raise ValueError(f"no editorial links found for contest {contest_id}")

    letter = problem_letter(problem_id)
    title_terms = problem_title_terms(problem_title)
    for link in links:
        normalized = link.text.lower()
        if normalized.startswith(f"{letter.lower()} ") or normalized.startswith(f"{letter.lower()} -"):
            return EditorialCandidate(link.text, link.url, "link_text_problem_letter")
        if title_terms and all(term in normalized for term in title_terms[:2]):
            return EditorialCandidate(link.text, link.url, "link_text_problem_title")

    official_english = [
        link
        for link in links
        if link.text.strip().lower() == "editorial"
        or "official editorial" in link.text.strip().lower()
    ]
    index = problem_index(problem_id)
    if 0 <= index < len(official_english):
        link = official_english[index]
        return EditorialCandidate(link.text, link.url, "nth_official_english_editorial")
    if 0 <= index < len(links):
        link = links[index]
        return EditorialCandidate(link.text, link.url, "nth_editorial_link")

    link = links[0]
    return EditorialCandidate(link.text, link.url, "first_editorial_link")


def editorial_links(page: WebPage, contest_id: str) -> list[WebLink]:
    seen: set[str] = set()
    links: list[WebLink] = []
    for link in page.links:
        if f"/contests/{contest_id}/editorial/" not in link.url:
            continue
        if link.url in seen:
            continue
        seen.add(link.url)
        links.append(link)
    return links


def problem_letter(problem_id: str) -> str:
    suffix = problem_id.rsplit("_", 1)[-1]
    return suffix[:1].upper() if suffix else "A"


def problem_index(problem_id: str) -> int:
    letter = problem_letter(problem_id)
    if len(letter) != 1 or not letter.isalpha():
        return 0
    return ord(letter) - ord("A")


def problem_title_terms(problem_title: str) -> list[str]:
    words = re.findall(r"[a-z0-9]{3,}", problem_title.lower())
    ignored = {"atcoder", "beginner", "regular", "grand", "contest"}
    return [word for word in words if word not in ignored]


def build_result(
    *,
    request: ProblemRequest,
    problem_title: str,
    candidate: EditorialCandidate,
    problem_page: WebPage,
    editorial_index_page: WebPage,
    editorial_page: WebPage,
    trace: list[dict[str, str | int]],
) -> dict[str, Any]:
    return {
        "contest_id": request.contest_id,
        "problem_id": request.problem_id,
        "problem_title": problem_title,
        "problem_url": problem_page.url,
        "editorial_index_url": editorial_index_page.url,
        "editorial_url": editorial_page.url,
        "editorial_title": editorial_page.title or candidate.title,
        "editorial_text_excerpt": editorial_page.text[:4000],
        "selection_strategy": candidate.strategy,
        "evidence": [
            {
                "url": problem_page.url,
                "reason": "Problem page confirms the requested problem and title.",
            },
            {
                "url": editorial_index_page.url,
                "reason": "Contest editorial index contains candidate editorial links.",
            },
            {
                "url": editorial_page.url,
                "reason": "Selected editorial detail page was opened directly from the contest editorial index.",
            },
        ],
        "webwalk_trace": trace,
    }


def ask_model_to_structure(
    *,
    request: ProblemRequest,
    problem_title: str,
    candidate: EditorialCandidate,
    problem_page: WebPage,
    editorial_index_page: WebPage,
    editorial_page: WebPage,
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
                        "task": "Return the official editorial information for one AtCoder problem.",
                        "request": request.__dict__,
                        "problem_title": problem_title,
                        "selected_editorial_candidate": candidate.__dict__,
                        "problem_page": compact_page(problem_page, max_links=20),
                        "editorial_index_page": compact_page(editorial_index_page, max_links=80),
                        "editorial_page": {
                            **compact_page(editorial_page, max_links=40),
                            "text_excerpt": editorial_page.text[:6000],
                        },
                        "required_shape": {
                            "contest_id": "string",
                            "problem_id": "string",
                            "problem_title": "string",
                            "problem_url": "string",
                            "editorial_index_url": "string",
                            "editorial_url": "string",
                            "editorial_title": "string",
                            "editorial_text_excerpt": "string",
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


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Find one AtCoder problem editorial via WebWalk.")
    parser.add_argument("contest_id", help="Contest id, for example abc220.")
    parser.add_argument("problem_id", help="Problem id, for example abc220_a.")
    parser.add_argument("--no-model", action="store_true", help="Run WebWalk extraction without calling the model.")
    args = parser.parse_args(argv)

    result = run_live_demo(args.contest_id, args.problem_id, use_model=not args.no_model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

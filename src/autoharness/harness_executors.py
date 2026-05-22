"""Task-aware AgentExecutor implementations for generated harnesses."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from autoharness.runtime import AgentDefinition


class AtCoderProblemEditorialExecutor:
    """Extract one AtCoder problem editorial from Runtime WebWalk observations."""

    def __init__(self, *, contest_id: str | None = None, problem_id: str | None = None) -> None:
        self.contest_id = contest_id
        self.problem_id = problem_id

    def dispatch(
        self,
        agent: AgentDefinition,
        input_source: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del agent
        tool_result = _require_tool_result(input_source)
        page = _require_page(tool_result)
        observations = [deepcopy(item) for item in current_payload.get("_observations", [])]
        observations.append(deepcopy(page))

        if len(observations) < 3:
            return {
                "_observations": observations,
                "webwalk_trace": deepcopy(tool_result["webwalk_trace"]),
            }

        problem_page, editorial_index_page, editorial_page = observations[-3:]
        contest_id = self.contest_id or _contest_id_from_url(problem_page["url"])
        problem_id = self.problem_id or _problem_id_from_url(problem_page["url"])
        problem_title = _problem_title(problem_page, problem_id)

        return {
            "contest_id": contest_id,
            "problem_id": problem_id,
            "problem_title": problem_title,
            "problem_url": problem_page["url"],
            "editorial_index_url": editorial_index_page["url"],
            "editorial_url": editorial_page["url"],
            "editorial_title": editorial_page.get("title") or _editorial_title_from_index(editorial_index_page, editorial_page),
            "editorial_text_excerpt": editorial_page.get("text_excerpt", ""),
            "selection_strategy": _selection_strategy(editorial_index_page, editorial_page, problem_id, problem_title),
            "evidence": [
                {
                    "url": problem_page["url"],
                    "reason": "Problem page was observed by Runtime WebWalk.",
                },
                {
                    "url": editorial_index_page["url"],
                    "reason": "Contest editorial index was observed by Runtime WebWalk.",
                },
                {
                    "url": editorial_page["url"],
                    "reason": "Selected editorial detail page was observed by Runtime WebWalk.",
                },
            ],
            "webwalk_trace": deepcopy(tool_result["webwalk_trace"]),
        }


class AtCoderLatestEditorialExecutor:
    """Extract the latest finished AtCoder contest editorial from WebWalk pages."""

    def dispatch(
        self,
        agent: AgentDefinition,
        input_source: Mapping[str, Any],
        current_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        del agent
        tool_result = _require_tool_result(input_source)
        page = _require_page(tool_result)

        if _is_archive_page(page):
            contest = _latest_contest_from_archive(page)
            return {
                "contest_id": contest["contest_id"],
                "contest_title": contest["contest_title"],
                "contest_url": contest["contest_url"],
                "editorial_url": f"{contest['contest_url'].rstrip('/')}/editorial",
                "evidence": [
                    {
                        "url": page["url"],
                        "reason": "AtCoder contest archive was observed by Runtime WebWalk.",
                    }
                ],
                "webwalk_trace": deepcopy(tool_result["webwalk_trace"]),
            }

        contest_id = str(current_payload.get("contest_id") or _contest_id_from_url(page["url"]))
        return {
            **deepcopy(dict(current_payload)),
            "editorial_url": page["url"],
            "problems": _editorial_links(page, contest_id),
            "evidence": [
                *deepcopy(list(current_payload.get("evidence", []))),
                {
                    "url": page["url"],
                    "reason": "Contest editorial page was observed by Runtime WebWalk.",
                },
            ],
            "webwalk_trace": deepcopy(tool_result["webwalk_trace"]),
        }


def _require_tool_result(input_source: Mapping[str, Any]) -> Mapping[str, Any]:
    if input_source.get("type") != "tool":
        raise ValueError("AtCoder executors require a tool input_source")
    data = input_source.get("data")
    if not isinstance(data, Mapping) or not isinstance(data.get("result"), Mapping):
        raise ValueError("AtCoder executors require Runtime tool results")
    return data["result"]


def _require_page(tool_result: Mapping[str, Any]) -> Mapping[str, Any]:
    page = tool_result.get("page")
    if not isinstance(page, Mapping):
        raise ValueError("WebWalk tool result must contain a page object")
    return page


def _is_archive_page(page: Mapping[str, Any]) -> bool:
    return "/contests/archive" in str(page.get("url", ""))


def _latest_contest_from_archive(page: Mapping[str, Any]) -> dict[str, str]:
    seen: set[str] = set()
    for link in page.get("links", []):
        if not isinstance(link, Mapping):
            continue
        url = str(link.get("url", ""))
        match = re.search(r"/contests/([a-z0-9_]+)$", url)
        if not match:
            continue
        contest_id = match.group(1)
        if contest_id in {"archive", "contests"} or contest_id in seen:
            continue
        seen.add(contest_id)
        return {
            "contest_id": contest_id,
            "contest_title": str(link.get("text") or contest_id),
            "contest_url": f"https://atcoder.jp/contests/{contest_id}",
        }
    raise ValueError("could not find a contest link in AtCoder archive observation")


def _editorial_links(page: Mapping[str, Any], contest_id: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in page.get("links", []):
        if not isinstance(link, Mapping):
            continue
        url = str(link.get("url", ""))
        if f"/contests/{contest_id}/editorial/" not in url or url in seen:
            continue
        seen.add(url)
        title = str(link.get("text") or "")
        links.append(
            {
                "title": title,
                "editorial_url": url,
                "kind": _editorial_kind(title),
                "language_guess": _editorial_language(title),
            }
        )

    official_links = [link for link in links if link["kind"] == "official"]
    return _with_problem_labels(official_links or links)


def _contest_id_from_url(url: str) -> str:
    match = re.search(r"/contests/([a-z0-9_]+)", url)
    if not match:
        return ""
    return match.group(1)


def _problem_id_from_url(url: str) -> str:
    match = re.search(r"/tasks/([a-z0-9_]+)", url)
    if not match:
        return ""
    return match.group(1)


def _problem_title(page: Mapping[str, Any], problem_id: str) -> str:
    title = str(page.get("title") or "")
    if " - AtCoder" in title:
        title = title.split(" - AtCoder", 1)[0]
    return title or problem_id


def _editorial_title_from_index(editorial_index_page: Mapping[str, Any], editorial_page: Mapping[str, Any]) -> str:
    editorial_url = str(editorial_page.get("url", ""))
    for link in editorial_index_page.get("links", []):
        if isinstance(link, Mapping) and link.get("url") == editorial_url:
            return str(link.get("text") or "")
    return ""


def _selection_strategy(
    editorial_index_page: Mapping[str, Any],
    editorial_page: Mapping[str, Any],
    problem_id: str,
    problem_title: str,
) -> str:
    editorial_url = str(editorial_page.get("url", ""))
    letter = _problem_letter(problem_id).lower()
    title_terms = _problem_title_terms(problem_title)
    for link in editorial_index_page.get("links", []):
        if not isinstance(link, Mapping) or link.get("url") != editorial_url:
            continue
        text = str(link.get("text") or "").lower()
        if text.startswith(f"{letter} ") or text.startswith(f"{letter} -"):
            return "link_text_problem_letter"
        if title_terms and all(term in text for term in title_terms[:2]):
            return "link_text_problem_title"
        return "selected_editorial_url"
    return "preconfigured_editorial_url"


def _problem_letter(problem_id: str) -> str:
    suffix = problem_id.rsplit("_", 1)[-1]
    return suffix[:1].upper() if suffix else "A"


def _problem_title_terms(problem_title: str) -> list[str]:
    words = re.findall(r"[a-z0-9]{3,}", problem_title.lower())
    ignored = {"atcoder", "beginner", "regular", "grand", "contest"}
    return [word for word in words if word not in ignored]


def _editorial_kind(title: str) -> str:
    normalized = title.strip().lower()
    if normalized in {"editorial", "official editorial"} or title.strip() == "\u89e3\u8aac":
        return "official"
    return "user"


def _editorial_language(title: str) -> str:
    normalized = title.strip().lower()
    if normalized in {"editorial", "official editorial"}:
        return "en"
    if title.strip() == "\u89e3\u8aac":
        return "ja"
    return "unknown"


def _with_problem_labels(links: list[dict[str, str]]) -> list[dict[str, str]]:
    labelled: list[dict[str, str]] = []
    problem_index = 0
    seen_languages: set[str] = set()
    for link in links:
        language = link.get("language_guess", "unknown")
        if labelled and (language == "unknown" or language in seen_languages):
            problem_index += 1
            seen_languages = set()
        seen_languages.add(language)
        labelled.append(
            {
                **link,
                "problem_label": chr(ord("A") + problem_index),
            }
        )
    return labelled

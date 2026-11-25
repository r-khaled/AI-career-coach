"""Split the current Markdown catalog at course boundaries, never at word counts.

This deliberately supports the catalog's nine-field schema, not arbitrary Markdown.
Malformed or unusually large records fail visibly instead of being truncated.
"""
import hashlib
import re

FIELDS = (
    "Course Name", "Track", "Level", "Estimated Duration", "Prerequisites",
    "Description", "Target Audience", "Skills Covered", "Learning Outcome and Assessment",
)
LEVELS = {"Foundation": 1, "Intermediate": 2, "Advanced": 3}
HEADING = re.compile(r"(?m)^### Course ID:[ \t]*([A-Z][A-Z0-9]*-\d+)[ \t]*$")
FIELD = re.compile(r"(?m)^\*\*([^*\n]+):\*\*[ \t]*(.+)$")
# An application guard, NOT a token measurement or an embedding-model limit.
MAX_COURSE_CHARACTERS = 6000
MAX_CONTEXT_CHARACTERS = 6000


def _chunk(body, metadata):
    return {"contentBody": body.strip(), "contentType": "TEXT", "contentMetadata": metadata}


def chunk_catalog(text):
    text = text.replace("\r\n", "\n").strip()
    matches = list(HEADING.finditer(text))
    if not matches:
        raise ValueError("No Course ID headings found; check the parser output")
    if text.count("### Course ID:") != len(matches):
        raise ValueError("Malformed Course ID heading")
    version = re.search(r"(?m)^Catalog version: ([\d.]+)\s*\|", text)
    if not version:
        raise ValueError("Missing catalog version")
    common = {
        "catalog_version": version.group(1),
        "parsed_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    chunks, courses, ids = [], [], set()
    # Preserve catalog-wide notes, omitting only structural track headings/separators.
    preamble = text[:matches[0].start()]
    preamble = re.sub(r"(?m)^## [^\n]+ Track\s*$", "", preamble).strip()
    if preamble:
        if len(preamble) > MAX_CONTEXT_CHARACTERS:
            raise ValueError("Catalog preamble needs its own subdivision policy")
        chunks.append(_chunk(preamble, {**common, "record_type": "catalog_context", "context_kind": "preamble"}))
    tail = ""
    for index, match in enumerate(matches):
        course_id = match.group(1)
        if course_id in ids:
            raise ValueError(f"Duplicate course ID: {course_id}")
        ids.add(course_id)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.start():end].strip()
        boundary = re.search(r"(?m)^(?:---[ \t]*$|## )", section)
        suffix = section[boundary.start():] if boundary else ""
        body = section[:boundary.start()].strip() if boundary else section
        if index < len(matches) - 1:
            # Between courses only a separator and a track heading are allowed.
            remainder = re.sub(r"(?m)^(?:---[ \t]*|## [^\n]+ Track)[ \t]*$", "", suffix).strip()
            if remainder:
                raise ValueError(f"Unclassified text after {course_id}")
        else:
            tail = re.sub(r"\A---\s*", "", suffix).strip()
        if len(body) > MAX_COURSE_CHARACTERS:
            raise ValueError(f"{course_id}: oversized record; add a within-course splitting policy")
        pairs = FIELD.findall(body)
        values = dict(pairs)
        if len(pairs) != len(FIELDS) or set(values) != set(FIELDS):
            raise ValueError(f"{course_id}: expected exactly the nine catalog fields")
        # No free text is silently dropped by the field extractor.
        if FIELD.sub("", body[body.index("\n") + 1:]).strip():
            raise ValueError(f"{course_id}: unsupported multiline or unstructured fields")
        if values["Level"] not in LEVELS:
            raise ValueError(f"{course_id}: unknown level")
        duration = re.fullmatch(r"([1-9]\d*) hours, including practice\.", values["Estimated Duration"])
        if not duration:
            raise ValueError(f"{course_id}: unsupported duration format")
        prerequisite_text = values["Prerequisites"]
        prerequisites = re.findall(r"\b[A-Z][A-Z0-9]*-\d+\b", prerequisite_text)
        if prerequisite_text != "None; suitable as an entry point.":
            if not prerequisites or ", ".join(prerequisites) != prerequisite_text:
                raise ValueError(f"{course_id}: unsupported prerequisite format")
        metadata = {
            **common, "record_type": "course", "course_id": course_id,
            "course_name": values["Course Name"], "track": values["Track"],
            "level": values["Level"], "level_rank": LEVELS[values["Level"]],
            "duration_hours": int(duration.group(1)), "has_prerequisites": bool(prerequisites),
        }
        if prerequisites:
            metadata["prerequisites"] = prerequisites
        courses.append(_chunk(body, metadata))
    for course in courses:
        for prerequisite in course["contentMetadata"].get("prerequisites", []):
            if prerequisite not in ids:
                raise ValueError(f"Unknown prerequisite: {prerequisite}")
    chunks.extend(courses)
    if tail:
        if len(tail) > MAX_CONTEXT_CHARACTERS:
            raise ValueError("Catalog notes need their own subdivision policy")
        chunks.append(_chunk(tail, {**common, "record_type": "catalog_context", "context_kind": "learning_paths_and_boundaries"}))
    return chunks

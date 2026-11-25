# Decision: course-aware custom chunking

[Architecture](../01-architecture.md) · [Deployment plan](../ingestion-deployment-plan.md)

Status: accepted design, deployed and validated with real Sync (zero failures), 42 indexed units, thirteen labelled top-five evidence cases plus one unsupported query, and metadata-filter tests. This is an initial dataset-specific check, not proof of optimal chunking or a generation-quality benchmark.

## 1. Start with business questions and source structure

We need both career-transition plans and precise course/prerequisite questions. Users chose exact level matching, strict track matching, and both per-course and total-plan hour limits; numeric caps are still unspecified. A course's identity, description, duration, level and prerequisites must remain coherent evidence.

The actual source is one 32,325-byte Markdown catalog, version 2.0: 40 fictional courses across ten tracks. Each starts at `### Course ID:` and repeats nine fields: name, track, level, estimated duration, prerequisites, description, audience, skills, outcome/assessment. Introductory guidance and coverage/learning-path notes are also knowledge and must not disappear.

The fields are extractable metadata embedded in text. They are not yet separate indexed metadata. File count is not a reliable reason to avoid preprocessing: splitting 10,000 records can be automated too.

## 2. Measure before selecting boundaries

Reproduce measurements using `chunk_catalog` from the repository root:

```python
from pathlib import Path
from statistics import median
from ingestion.course_chunker import chunk_catalog
courses = [c for c in chunk_catalog(Path("internal_courses.md").read_text())
           if c["contentMetadata"]["record_type"] == "course"]
words = [len(c["contentBody"].split()) for c in courses]
print(len(courses), min(words), median(words), max(words))
# 40 77 82.0 97
```

This counts whitespace-separated words in the emitted body, INCLUDING Course ID heading and field labels. Character counts are 632–806, median 704. Earlier approximations used different boundaries and must not be compared as though they were tokens. We did not measure model-token counts; there is no basis for claiming that a course necessarily spans several 300-token chunks. Median summarizes the distribution; it does not determine an optimal chunk size by itself.

## 3. Alternatives considered

- **Default / fixed-size:** a simple baseline, but token limits and overlap do not guarantee course boundaries or correct single-course metadata. This is a structural concern, not proof that default retrieval is poor. No benchmark was run.
- **Hierarchical:** useful when small evidence needs a larger parent context; automatic parents are not necessarily courses, can mix records, and do not solve reliable record metadata. Current short complete records do not establish a need for parent expansion.
- **Semantic:** useful for long prose with topic shifts; semantic boundaries are not guaranteed to coincide with course records. Our explicit IDs provide a clearer deterministic boundary. Added processing is not justified by measured relevance improvements yet.
- **One file per course:** a valid automated upstream design with document-level metadata and possibly NONE without a splitting hook. Rejected for THIS lab to retain one source and learn custom ingestion, not because 40/10,000 files are inherently impossible or undesirable.
- **Chosen:** one original file, default parser, built-in NONE and a course-aware Transformation Lambda.

## 4. Exact selected policy and its trade-offs

Identify each Course ID, validate the nine-field schema and prerequisite IDs, retain the entire short course, extract typed metadata and emit one record per course. Keep zero overlap between different courses. Preserve the introduction and final notes as two distinct context records. Output 42 records, not 42 courses and not 40 new source objects.

Chunking defines the logical retrieval units. Batching puts units into JSON transport files (`fileContents`). The current hook writes one output batch per source invocation. Bedrock reads that reference and continues embedding/indexing. It is not an upstream file-splitting cron job and not a query-time retriever.

Trade-off: extra Lambda/IAM/intermediate storage, a schema-specific parser, monitoring and an additional failure boundary in exchange for deterministic record integrity and reliable metadata. Source remains unchanged. Oversized records are rejected; they do not get silently split or truncated. A future within-course policy must repeat course identity/metadata and use a measured token budget. Character guards (6,000 per record/context, 2 MB total parsed input, 20 batches) are operational lab limits, not embedding limits or a validated large-catalog design.

## 5. Evaluate evidence before generation

After a successful real Sync, use the same source version, embedding model, vector settings, queries and context budget to compare policies. Start with Retrieve top five, inspect course identity, complete facts/prerequisites, rank, duplicate evidence and cross-track coverage. A structurally intact course chunk is not proof that it will rank correctly.

Run representative questions across all tracks, precise prerequisites, multi-course requests and an unsupported profession. Retrieve can return neighbors for an unsupported question; an empty result array is not a prerequisite for correct refusal. Test English first to isolate boundaries, then Arabic separately.

Test filters independently: record_type=course, exact level, exact track and numeric per-course hours. Compute total-plan hours over distinct selected courses in application logic later. Report out-of-scope prerequisites rather than adding excluded courses. The existing application does not enforce these rules yet. Do not attribute improvement from newly added metadata to chunk size alone.

[Bedrock custom transformation contract](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-custom-transformation.html)

Integration correction: source and intermediate storage must be separate S3 buckets (validated by CreateDataSource rejection). The course boundaries and metadata policy did not change. Real Sync also requires the KB-scoped Bedrock Lambda resource permission.

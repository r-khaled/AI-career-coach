# Knowledge pipeline and data contracts

[Documentation](README.md) · [Architecture](architecture.md) · [Chunking decision](decisions/course-aware-chunking.md)

## Source catalog

`internal_courses.md` contains 40 synthetic courses across ten tracks with a catalog-version declaration. Each record starts with `### Course ID: TRACK-NNN` and has nine fields: Course Name, Track, Level, Estimated Duration, Prerequisites, Description, Target Audience, Skills Covered, and Learning Outcome and Assessment.

The source is one object, not a directory of per-course files. Source inclusion is `internal_courses.md`; deployment artifacts under `lambda-artifacts/` are not source documents. The transformation adapter validates the exact source URI, so adding arbitrary objects or another catalog requires an intentional contract/configuration change.

## Parsing and custom evidence boundaries

The KB uses the default text parser and built-in chunking NONE with a POST_CHUNKING transformation hook. The parser converts source content into text/JSON batches. Bedrock writes those batches to the separate intermediate bucket and passes their references to Lambda. Lambda reassembles the parsed catalog, validates its structure and emits one complete unit per Course ID, plus two catalog-wide context units.

This custom extraction keeps names, descriptions, level, duration and prerequisites together and adds typed metadata. It does not call the embedding model itself. Chunking defines the evidence units; batching groups those units for transport. Current output is 42 records in intermediate JSON, not 40 new source objects. There is no overlap across courses.

The supported guards are 6,000 characters per course/context, aggregate parsed input of 2,000,000 bytes per source file and at most 20 incoming batches. These are implementation guards, not token measurements or the Titan input limit. Oversized or unsupported schemas fail rather than truncate. Ten-thousand-course scaling has not been established; it needs bounded processing, within-course policy and load/quality tests.

## Metadata

Course units include these types:

- `record_type`: string `course`; context units use `catalog_context` and a context_kind.
- `course_id`, `course_name`, `track`, `level`, `catalog_version`, `parsed_source_sha256`: strings.
- `level_rank`: numeric rank Foundation=1, Intermediate=2, Advanced=3.
- `duration_hours`: positive integer extracted from the defined duration grammar.
- `has_prerequisites`: boolean; `prerequisites`: nonempty string list when required.

The original Markdown fields are text until extraction produces indexed metadata. Their presence inside a document does not automatically make them filterable. Unexpected inherited chunk metadata is rejected pending a deliberate merge policy. The parsed-source hash identifies the normalized text, distinct from the original object-byte hash in the build manifest.

Metadata supports exact filters, but the current application does not send strict business filters. Exact level, strict track, per-course hours and total-plan hours require explicit request validation, retrieval filters and deterministic post-validation. A course outside the allowed track must not be silently added to cover prerequisites; requirements not covered by the selected constraints must be reported.

## Embeddings and vector index

Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`) produces FLOAT32 vectors of 1024 dimensions. The companion template creates an OpenSearch Serverless faiss/HNSW index with matching vector dimension, stored text and stored metadata. Field mappings are `vector`, `text` and `metadata` in new template-managed deployments; reused existing indices can have different physical names if their Bedrock configuration is valid. Do not change dimensions without matching/rebuilding the index.

42 raw vectors occupy `42 × 1024 × 4 = 172,032` bytes before index/text/metadata/replica overhead; this is not the measured billable footprint. Embedding tokens are billed during ingestion of changed content and during query embedding. OpenSearch stores/searches the vectors; the original documents remain in S3. Neither indexing nor saved conversations updates model weights.

## Initial, manual and scheduled refresh

First-use setup provisions/reuses the KB, binds its service-to-Lambda permission, creates/validates the data source and starts Sync immediately. Manual `sync --apply` works on content already in S3 and does not upload local edits. Weekly Scheduler calls StartIngestionJob for the same source; Bedrock detects changes and performs the ingestion stages. An unchanged weekly source is not assumed to be fully re-embedded every week, although listing/checking/control-plane work remains.

Bedrock service-role access is separate from hook-runtime access. The KB role reads source, manages intermediate content, invokes the hook and Titan and accesses the vector index. Lambda only reads/writes the permitted intermediate prefix and logs. Source and intermediate buckets must be different. [Permissions](security.md).

## Retrieval acceptance

Run Retrieve before RetrieveAndGenerate. Example SDK request, using the KB ID produced by setup:

```python
import boto3
runtime = boto3.Session(profile_name="YOUR_PROFILE", region_name="us-east-2").client("bedrock-agent-runtime")
response = runtime.retrieve(
    knowledgeBaseId="KB_ID_FROM_SETUP",
    retrievalQuery={"text": "Which course covers identity, authentication and authorization?"},
    retrievalConfiguration={"vectorSearchConfiguration": {
        "numberOfResults": 5,
        "filter": {"equals": {"key": "record_type", "value": "course"}},
    }},
)
for result in response["retrievalResults"]:
    print(result.get("metadata"), result["content"]["text"])
```

Check all expected IDs/complete bodies, distinct results, required prerequisites, source citations and metadata types. Use a labelled set spanning tracks and transition queries; include unsupported questions and impossible filter combinations. Semantic search can return nearest neighbours for unsupported roles; it does not guarantee refusal.

For strict filtering, combine record_type, exact level and track with a numeric duration_hours limit using `andAll`, `equals` and `lessThanOrEquals`. An Intermediate filter means Intermediate only, not Foundation automatically. Total-plan duration is an aggregate application constraint; a per-record duration filter does not enforce it.

A COMPLETE job with failed documents is not accepted. Index visibility can lag Sync; inspect count/output and retry bounded reads before changing chunking or re-ingesting. The built-in setup smoke check is one filtered known-ID check; it must not be reported as a full benchmark.

## Generation boundary

The application calls RetrieveAndGenerate with top five evidence records and maxTokens 800. Generation receives the prompt and retrieved context, then returns text/citations for persistence. The ingestion hook does not run here. Lower request limits, prompt changes or a different generation model do not change the already indexed chunks. Parser/chunking/embedding changes require a deliberate data-source/index migration and retrieval regression evaluation.

References: [custom transformation contract](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-custom-transformation.html), [Titan v2 model](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html).

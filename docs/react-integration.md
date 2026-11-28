# Guided planning React integration

> **Contract handoff — reviewed 2026-11-28:** Schema version 1.0; version anchor `react-contract-v1`. Backend and offline conformance are implemented. No production React screens or running reference API are included; build locally with mocks, then authorize deployment separately.

React owns display and unsent drafts. The backend owns the current question, profile, review, versions, jobs and plans. These endpoints are same-origin Flask routes; React must never call API Gateway or Bedrock directly or receive AWS credentials, Serper keys, or the anonymous session proof. The shipped Flask proxy and tests are a backend handoff, not a production React UI.

## Configuration and sessions

Set `PUBLIC_ORIGIN` to the exact browser origin, such as `https://coach.example.com`, and `API_BASE_URL` to the API Gateway stage URL, such as `https://api.example.com/prod`. If `API_BASE_URL` is unset, Flask derives it from legacy `API_URL` only when that ends in `/generate-plan`. Server-side AWS credentials and region must support SigV4 `execute-api`. Production requires HTTPS. For local HTTP only, explicitly set `GUIDED_ENV=development`, `PUBLIC_ORIGIN=http://localhost:5001`, and a localhost HTTP `API_BASE_URL`; otherwise cookies are Secure. Use HTTPS outside local development.

The browser must send an exact matching `Origin` for every POST; missing, `null`, and other origins are rejected. Flask issues an opaque HttpOnly, SameSite=Lax cookie, Secure on HTTPS, renewed for seven days after successful activity. It contains the session identifier and proof; JavaScript cannot read the proof. Same-browser cookie loss or expiry prevents recovery. New session replaces the current cookie. A successful session response contains `session_id`, `state` (dialogue-response contract) and `profile` separately.

```js
const base = '/api/v2';
async function api(path, options = {}) {
  const res = await fetch(base + path, {
    credentials: 'same-origin', ...options,
    headers: {'Content-Type': 'application/json', ...options.headers}
  });
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.error?.message || 'Request failed'), {status: res.status, data});
  return {status: res.status, data};
}
const create = () => api('/sessions', {method: 'POST', body: '{}'});
const resume = () => api('/session');
```

Render `state.next_question` and keep its `question_id` and `state_version`. Serialize choices and numbers as text in `answer`. A user can answer multiple objectives; only the backend decides the next question.

```js
const requestId = crypto.randomUUID();
const answer = {question_id, answer: answerText, state_version, request_id: requestId};
const response = await api(`/sessions/${sessionId}/answers`, {
  method: 'POST', body: JSON.stringify(answer)
});
```

`200` contains the next state. `202` means the same request is processing; retry the **same request ID and identical body**. The same rule applies after an uncertain network failure. A `409` stale/conflict response requires resume and reconciling displayed state; do not blindly resubmit changed content under the same ID. A terminal `503` may be retried as a new request ID only after the backend has reported terminal failure; if outcome is uncertain retry the original ID first. A `403` or `410` may clear the cookie; start a new session when appropriate.

## Review and plan jobs

When `state.status` is `review_required`, show assumptions and unresolved items. Approve using the exact displayed state version and selected assumption IDs:

```js
await api(`/sessions/${sessionId}/review`, {method:'POST', body: JSON.stringify({
  state_version, confirmed_assumption_ids: selectedIds
})});
```

Corrections use optional `corrections: [{key, value}]`. They invalidate approval and require a subsequent review and explicit confirmation. Do not interpret inferred facts as confirmed or silently specialize an unresolved goal. Submit a plan only after approval, binding it to `profile.profile_version`:

```js
const submission = {request_id: crypto.randomUUID(), profile_version: profile.profile_version};
const {data: job} = await api(`/sessions/${sessionId}/plans`, {
  method:'POST', body:JSON.stringify(submission)
}); // 202, strict job object
```

Poll `GET /sessions/{sessionId}/jobs/{jobId}` starting at 2 seconds, increasing to 5 seconds with jitter and a client timeout. Use `status` and `stage`; do not invent a percentage. On timeout, allow the user to resume polling the same job. A job uses an immutable approved-profile snapshot; edits while it runs do not mutate that snapshot. Compare the job/plan `profile_version` with the current profile and display stale results where they differ (also honor `stale_profile` if present). On `failed`, show the safe error and allow an intentional new submission with a new ID.

When completed, read `GET /sessions/{sid}/plans/{planId}?revision=1`. Download using `/download?revision=1&format=json` or `format=markdown`; Flask fetches and validates the same structured plan and includes assumptions, evidence, versions, time budget and gaps. Do not parse old numbered text as a roadmap. A revision uses `POST /sessions/{sid}/plans/{planId}/revisions` with `{request_id, base_revision, profile_version, change_request}` and returns a new job. Preserve old revisions, show consequences, and use the latest completed revision as the base; an older base returns 409.

## Local conformance

`tests/test_guided_proxy.py` exercises Flask with injected offline services and fake model/providers. Cloud deployment, real React screens, live retrieval, live model quality and cost/latency acceptance remain separate work. Never log raw answers, cookies, proof tokens, provider secrets or full provider errors.

A session permits at most eight plan jobs in total, including the initial plan and revisions. The session state is limited to 96 KiB and a cached response to 64 KiB. If a session reaches its job limit, start a new session to submit further jobs; download plans first for user retention.

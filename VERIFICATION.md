# Verification record

Updated 10 November 2026 for bundle v1.1.0, from the uploaded conference app.

- Python 3.12; installed API pins are in `requirements.txt`, with the complete
  resolved environment in `requirements.lock.txt`.
- 93 pytest cases and 65 subtests passed.
- Real Agent Framework/OpenAI adapter exercised through an in-memory HTTP
  Responses transport, including tool calls, returned reasoning summaries and two
  successive requests with closed client contexts. Covers Demo 1 and both the
  normal and bad-fixture live paths of Demo 2.
- Demo 2 regression cases cover GET-to-POST selection, query fallback, explicit
  body precedence, selector validation in both engines, original-output retention,
  unchanged normal live evaluation and provider errors that remain HTTP 502.
- Fixture-mode browser checks passed for all three apps: delayed tool, unavailable
  weather, passing/failing candidates (200/422), downloaded evaluation bundle,
  benign request and pre-agent rejection (200/403).
- Demo 2 live-mode browser checks passed with an injected planner and the real
  simulated tools: bad selector preserved in form/query, labeled FAIL/422,
  original response/reasoning retained, downloaded candidate/provenance hashes
  verified, normal output unchanged and hidden-field-only submission supported.
  Exactly one planner operation and one invocation of each tool per submission.
- The browser-exported good candidate/contract passed the separate CLI gate
  (exit 0); the exported live-mode injected bad candidate was rejected (exit 1).
- Mobile layouts checked at 390-pixel width, without horizontal overflow or
  JavaScript page errors.
- The blocked-request integration check asserts zero planner/SDK-client calls and
  only the request/security-check spans.

Model HTTP requests were mocked. No real model deployment, Foundry guardrail
configuration, New Relic account or GitHub Actions workflow was executed during
preparation. Rehearse those actual connections before presenting.

Uploaded source SHA-256: `865818d64759211bc6e5174a1182014823b5b482e70e997bf36ab1460135c5a3`.

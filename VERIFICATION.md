# Verification record

Updated 13 November 2026 for bundle v1.2.0 and the optional multi-agent workflow.

- Python 3.12; installed API pins are in `requirements.txt`, with the complete
  resolved environment in `requirements.lock.txt`.
- 121 pytest cases and 65 subtests passed across the original flows and the
  Destination → Conditions → Itinerary workflow.
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
- Multi-agent SDK tests verify three distinct agents/clients, tool isolation,
  evidence-checked typed handoffs, a single trace, sequential stages, exact
  counters, repeated-request cleanup, duplicate-call rejection and one cumulative
  workflow deadline. Invalid intermediate handoffs prevent later agents.
- Browser checks passed for the three multi-agent fixture flows and for the live
  route using all three actual SDK agents with mocked HTTP: PASS/FAIL rendering,
  stage/handoff display, evaluation downloads, original Itinerary output and
  agent-labeled summaries. Six client lifetimes closed across two requests.
- Exported multi-agent good/bad candidates return 0/1 from the independent gate.
  Mobile rendering at 390 pixels has no horizontal overflow or JavaScript errors.

Model HTTP requests were mocked. No real model deployment, Foundry guardrail
configuration, New Relic account or GitHub Actions workflow was executed during
preparation. Rehearse those actual connections before presenting.

Uploaded source SHA-256: `865818d64759211bc6e5174a1182014823b5b482e70e997bf36ab1460135c5a3`.

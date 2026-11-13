# Destination → Conditions → Itinerary

The multi-agent workflow implements the specialist design from the Porto slides
using three actual Microsoft Agent Framework agents and a small sequential
Python coordinator. Each stage finishes and validates its result before the next
agent is created. It uses direct awaited agent calls rather than a dynamic
supervisor or an unbounded conversation between agents.

| Agent | Registered tools | Output or responsibility |
| --- | --- | --- |
| Destination | `get_random_destination` | Typed `DestinationHandoff`, confirming the authorized Porto destination |
| Conditions | `get_weather`, `get_datetime` | Typed `ConditionsHandoff`, matching the weather/time evidence actually recorded by the tools |
| Itinerary | None | The final answer, based on the request and validated handoffs |

The destination remains fixed to Porto and weather remains simulated. There are
no booking, payment, or external-write tools. This demonstrates orchestration,
handoff validation and observability; it does not add durable transaction state.

## Run it

Use Python 3.12 and install the existing verified environment. Keep an existing
configured `.env`; the copy commands below create it only when it is absent.
From the repo:

```bash
python -m pip install -r requirements.lock.txt
if [ ! -f .env ]; then cp .env.example .env; fi
```

For Windows PowerShell:

```powershell
python -m pip install -r requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

For offline rehearsal in Bash:

```bash
DEMO_ENGINE=fixture python web_app_multiagent.py --demo 2
```

Or PowerShell:

```powershell
$env:DEMO_ENGINE = "fixture"
python .\web_app_multiagent.py --demo 2
```

Open http://127.0.0.1:5005. For actual model calls, configure the same model
endpoint, key and deployment used by the original apps, then launch with
`DEMO_ENGINE=live`. In PowerShell, set `$env:DEMO_ENGINE = "live"` before launch.
Your model/API must support structured JSON output for the first two handoffs;
leave unsupported reasoning options blank as described in the main README.

`--demo 1` keeps the trace-focused flow, `--demo 2` adds the existing acceptance
checks and evaluation download, and `--demo 3` checks the input before starting
any agent. The launcher forces multi-agent mode and defaults to Demo 2.
`PORT` can override its default port 5005.

To keep the existing entry points and ports instead:

```bash
DEMO_WORKFLOW=multi python web_app_demo1.py  # port 5002
DEMO_WORKFLOW=multi python web_app_demo2.py  # port 5003
DEMO_WORKFLOW=multi python web_app_demo3.py  # port 5004
```

In PowerShell, set `$env:DEMO_WORKFLOW = "multi"`, then run the desired script.
The original paths remain available with `DEMO_WORKFLOW=single` (the default).
Engine and workflow are server configuration, not client-controlled form fields.
The UI banner and `/health` report the selected workflow and execution engine.

## What happens at each handoff

The Destination agent must call its one registered tool. Its structured result
must confirm Porto and match the destination evidence in the request context.
It cannot call the weather or time tools.

The Conditions agent receives that validated destination. It must call weather
and time exactly once each. Its structured weather fields and `observed_at`
timestamp must match the recorded tool results. Unavailable weather is a valid
handoff with explicit unavailable status and null forecast fields; inventing
conditions is a rejected handoff.

Pydantic models forbid extra fields, and application checks compare their values
with actual tool evidence. The coordinator also checks required tool invocation
and rejects duplicate attempts. A model claiming it called a tool cannot create
evidence. Invalid handoffs stop the workflow before the next agent is created.

The Itinerary agent receives the validated handoffs and the trip request as JSON
data. Its system instructions treat user fields as untrusted. It has no tools.
Demo 2 evaluates its final answer using the existing `quality.py` contract;
invalid final JSON or unmet requirements remain quality failures (HTTP 422).
Failed intermediate handoffs, model errors and workflow timeouts return the
controlled technical-error response (HTTP 502).

The coordinator allows three agent stages and uses one `PLANNER_TIMEOUT_S`
deadline for the entire workflow, not a new full deadline per agent. Existing SDK
tool-loop limits still apply within each stage. Three agents add model calls,
latency and token usage; choose a model/deadline appropriate for your deployment.
Every agent uses a fresh async client closed on the request's event loop.

## Trace the workflow

The application and SDK share the current OpenTelemetry context through the
awaited stages. The conceptual hierarchy is:

```text
plan_trip
├── security.prompt_injection_check     # Demo 3, before workflow execution
└── plan_trip_request
    └── travel_workflow
        ├── agent.destination
        │   └── Destination agent / model / destination tool spans
        ├── agent.conditions
        │   └── Conditions agent / model / weather and time tool spans
        └── agent.itinerary
            └── Itinerary agent / model spans; no tool calls
```

The wrapper spans use application attributes such as `app.agent.name` and
`app.execution.mode`. They add a stable business boundary around the SDK's actual
agent/model/tool spans. Handoff validation is observable without exporting raw
user text by default. Returned reasoning summaries, if enabled and supplied by
the model, are labeled by the agent that produced them.

Custom counters `travel_plan.agent_steps.total` and
`travel_plan.agent_handoffs.total` complement existing request, tool, quality and
security instruments. Their dimensions remain bounded. The result UI displays
each agent's tool boundary and the validated handoff payloads. Demo 2's downloaded
bundle includes these stages and handoffs alongside the evaluated candidate,
contract and trace reference; `export_run.py` and the offline gate still work.

Fixture mode executes the simulated tools and validates the same handoff types,
but uses fixture stage outputs instead of making model calls. Its spans/UI are
explicitly labeled as fixture execution; it does not fabricate SDK model spans.

## Exercise the existing failure paths

- Demo 1: use **Slow weather lookup** and **Weather unavailable**. The failed
  weather implementation remains visible even if the answer acknowledges
  uncertainty successfully.
- Demo 2: `/?fixture=bad&delay_scale=0` still exercises the deterministic rejection.
  In live mode, all three agents complete first; the existing labeled
  `inject_bad_candidate` step then substitutes the evaluated candidate. Original
  Itinerary output, stage summaries and handoffs remain separate from that fixture.
- Demo 3: `/?sample=attack&delay_scale=0` still returns 403 before creating any
  agent or client. The trace contains the request/security check, with no
  `travel_workflow` or agent-stage spans.

## Code and verification

`multi_agent.py` owns the agents, typed handoffs and coordinator. `demo_common.py`
selects the configured runner and owns the existing tools/context/instruments.
The dedicated routes retain their trace, evaluation and enforcement behavior.

Run `python -m pytest -q`. Integration tests use real Agent Framework/OpenAI
adapters with mocked Responses HTTP, including scoped tools, typed output,
sequential client lifetimes, trace relationships and rejected handoffs. They do
not contact a real model or telemetry account. Rehearse your configured live
deployment before relying on it for a talk or customer demonstration.

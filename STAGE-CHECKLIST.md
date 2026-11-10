# Stage checklist — Porto Tech Hub

Use the README for setup before conference day. After adding “Who am I” as slide 2,
the demo cue slides are 14, 22 and 27. Start the apps and prepare backend traces
before the session. Use synthetic inputs; keep the filled `.env` off screen.

**v1.1.0 upgrade:** Replace the whole bundle, stop any older app processes, then
restart. Check **v1.1.0** in each page footer and `pack_version` in `/health`.
Mixing old templates/shared files with a new entry point can hide the fix.

On Windows PowerShell, select the engine explicitly before launching an app:

```powershell
# Real SDK/model, after configuring the private .env.
$env:DEMO_ENGINE = "live"
python .\web_app_demo2.py
```

For the offline alternative, stop the app and relaunch:

```powershell
$env:DEMO_ENGINE = "fixture"
python .\web_app_demo2.py
```

Change the entry point for the other demos. The environment setting persists in
that terminal; changing `.env` alone may not change the selected engine.

## Demo 1 — 5 minutes · slide 14

```bash
DEMO_ENGINE=fixture python web_app_demo1.py
```

1. Open http://127.0.0.1:5002 → **Slow weather lookup** → submit.
2. Copy the trace ID and find the 3.5-second `get_weather` implementation span.
3. Select **Weather unavailable**, submit, and inspect its error span and returned
   unavailable evidence.
4. Compare the honest uncertainty in the answer with the dependency outcome.

**Say:** “Weather is simulated. In fixture mode, the planner is simulated too;
a live SDK/model run produces the framework’s real model/tool spans.”

## Demo 2 — 4 minutes · slide 22

```bash
DEMO_ENGINE=live python web_app_demo2.py
```

1. Open http://127.0.0.1:5003/?fixture=good&delay_scale=0 and submit. This evaluates
   the actual model output. It may pass or fail; the selector does not force PASS.
2. Open http://127.0.0.1:5003/?fixture=bad&delay_scale=0 and submit. The actual
   SDK/model and tools run once, then the app explicitly substitutes the synthetic
   bad-plan candidate. Expect FAIL / HTTP 422 after a successful model run.
3. Show the failed day-sequence, interest and weather-evidence checks. Keep the
   original model output/reasoning separate from the injected candidate. In the
   trace, find `inject_bad_candidate` and `app.demo.output_substituted=true`; the
   real model/GenAI output is preserved. Provider failure remains HTTP 502.
4. Run the independent, offline gate in a prepared terminal:

```bash
python release_gate.py --candidate fixtures/good-plan.json --contract fixtures/contract.json --report reports/good.json
echo $?
python release_gate.py --candidate fixtures/bad-plan.json --contract fixtures/contract.json --report reports/bad.json
echo $?
```

Expected exits: `0`, then `1`. Use `$LASTEXITCODE` in PowerShell.
The gate also accepts candidate/contract files extracted from the browser's
**Download evaluation bundle** with `export_run.py`.

**Say:** “A completed model call can still fail the product contract. These are
hard checks of structured fields and observed evidence. For this request I
deliberately injected the bad candidate after the real model run; it is not the
model's original answer or a factuality score.”

**Offline alternative:** Restart with `DEMO_ENGINE=fixture`. The same good/bad
URLs then use offline fixtures only: good → PASS / 200; bad → FAIL / 422. No live
model call occurs. Identify the mode switch clearly. The submitted form retains
the fixture selector and controls in both its action query and hidden fields;
posted form/JSON values take precedence over the query.

## Demo 3 — 4 minutes · slide 27

```bash
DEMO_ENGINE=fixture python web_app_demo3.py
```

1. Open http://127.0.0.1:5004 → **Benign request** → submit → HTTP 200.
2. Select **Instruction override** → submit → HTTP 403.
3. Point to the score, matched categories and policy version.
4. Verify the request/security-check spans and absence of planner, agent, model
   and tool work. Compare with the benign trace.

**Say:** “This heuristic catches the selected fixture. The control matters
because it returns before the agent runs. It does not prove general protection.”

## Live run and fallback

For actual model calls, set `DEMO_ENGINE=live`, configure your deployed model and
rehearse it privately. If live services fail, restart with fixture mode and
identify that switch clearly, or use the slide fallback. Do not call fixture
spans live LLM telemetry. Never install dependencies or debug credentials on stage.
The bundle was verified with mocked SDK tests and browser checks, not a real
model endpoint or New Relic account. Confirm those connections before conference day.

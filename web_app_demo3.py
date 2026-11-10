"""Demo 3: classify the synthetic attack and enforce the decision BEFORE work.

Run: python web_app_demo3.py (http://127.0.0.1:5004)
This heuristic detector is a teaching aid, not general injection protection.
"""
import time
from flask import current_app
from demo_common import (InputError, create_base_app, dimensions, execute_planner,
                         log_event, parse_trip, plan_payload, record_outcome,
                         reject_input, request_scope, respond, start, technical_failure)
from security import detect_prompt_injection


def create_app():
    app = create_base_app('3', 'Block the unsafe request before the agent runs')

    @app.post('/plan')
    async def plan_trip():
        with request_scope() as span:
            try:
                trip = parse_trip()
                metrics = current_app.extensions['demo_metrics']
                started = time.perf_counter()
                with current_app.extensions['tracer'].start_as_current_span('security.prompt_injection_check') as security_span:
                    # Validate structured fields first; scan every remaining free-text field.
                    text = '\n'.join([trip.special_requests, *trip.interests])
                    decision = detect_prompt_injection(text)
                    elapsed = time.perf_counter() - started
                    metrics['security_scanned'].add(1, dimensions())
                    metrics['security_score'].record(decision['risk_score'], dimensions())
                    metrics['security_latency'].record(elapsed, dimensions())
                    if decision['patterns']:
                        metrics['security_detected'].add(1, dimensions())
                    outcome = 'blocked' if decision['blocked'] else 'allowed'
                    attrs = {'app.security.decision': outcome,
                             'app.security.risk_score': decision['risk_score'],
                             'app.security.policy.version': decision['policy_version']}
                    security_span.set_attributes(attrs)
                    span.set_attributes(attrs)
                    log_event('security_decision', **attrs,
                              **{'app.security.patterns': ','.join(decision['patterns'])})
                if decision['blocked']:
                    metrics['security_blocked'].add(1, dimensions())
                    record_outcome(span, 'security_blocked')
                    # Enforcement lives here. No tools, SDK client or agent are created.
                    return respond({'error': 'This request was blocked by the demo security policy.',
                                    'security': decision}, 'error.html', 403)
                run = await execute_planner(trip, hardened=True)
                record_outcome(span, 'success')
                return respond({**plan_payload(run, trip), 'security': decision})
            except InputError as error:
                return reject_input(span, error)
            except Exception as error:
                return technical_failure(span, error)

    return app


app = create_app()
if __name__ == '__main__':
    start(app, 5004)

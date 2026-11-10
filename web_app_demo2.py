"""Demo 2: a completed answer can fail the trip contract; gate it explicitly.

Run: python web_app_demo2.py (http://127.0.0.1:5003)
Offline CI gate: python release_gate.py --help (no model calls).
"""
import hashlib
from flask import current_app
from demo_common import (DEMO_PACK_VERSION, ROOT, InputError, create_base_app, dimensions, execute_planner,
                         fixture_selection,
                         log_event, parse_trip, plan_payload, record_outcome,
                         reject_input, request_scope, respond, start, technical_failure)
from quality import CandidateParseError, evaluate_plan, parse_candidate


def evaluation_input(run, span):
    """Keep SDK output truthful; inject a labeled candidate only after live success."""
    fixture = fixture_selection()
    substituted = run.engine == 'live' and fixture == 'bad'
    source = ('bad_fixture_after_live_model' if substituted else
              f'{fixture}_fixture' if run.engine == 'fixture' else 'live_model')
    provenance = dict(engine=run.engine, fixture=fixture, candidate_source=source,
                      output_substituted=substituted, pack_version=DEMO_PACK_VERSION)
    text = run.text
    original = dict(original_model_output=None, original_model_candidate=None)
    attributes = {'app.demo.output_substituted': substituted,
                  'app.evaluation.candidate_source': source, 'app.demo.fixture': fixture}
    if substituted:
        with current_app.extensions['tracer'].start_as_current_span('inject_bad_candidate') as injection:
            fixture_bytes = (ROOT / 'fixtures/bad-plan.json').read_bytes()
            text = fixture_bytes.decode('utf-8')
            provenance.update(fixture_path='fixtures/bad-plan.json',
                              fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
                              original_model_output_sha256=hashlib.sha256(run.text.encode('utf-8')).hexdigest())
            original['original_model_output'] = run.text
            try:
                original['original_model_candidate'] = parse_candidate(run.text)
            except CandidateParseError as error:
                provenance['original_model_parse_error'] = str(error)
            injection.set_attributes({**attributes,
                                      'app.demo.fixture_sha256': provenance['fixture_sha256'],
                                      'app.demo.original_output_sha256': provenance['original_model_output_sha256']})
            log_event('bad_candidate_injected', **attributes)
    span.set_attributes(attributes)
    return text, provenance, original


def create_app():
    app = create_base_app('2', 'Reject a plausible answer and block promotion')

    @app.post('/plan')
    async def plan_trip():
        with request_scope() as span:
            try:
                trip = parse_trip()
                run = await execute_planner(trip, structured=True)
                candidate_text, provenance, original = evaluation_input(run, span)
                contract = dict(destination='Porto', duration_days=trip.duration,
                                interests=list(trip.interests), weather=run.evidence.get('weather'))
                with current_app.extensions['tracer'].start_as_current_span('evaluate_trip') as evaluation_span:
                    evaluation_span.set_attribute('app.evaluation.candidate_source', provenance['candidate_source'])
                    candidate = None
                    try:
                        candidate = parse_candidate(candidate_text)
                    except CandidateParseError as error:
                        result = dict(passed=False, checks=[], issues=[str(error)],
                                      error_type='candidate_parse_error')
                    else:
                        if not isinstance(contract['weather'], dict):
                            result = dict(passed=False, checks=[], issues=['No weather tool evidence was recorded.'],
                                          error_type='missing_tool_evidence')
                        else:
                            result = evaluate_plan(candidate, contract)
                    evaluation_span.set_attribute('app.evaluation.passed', result['passed'])
                    evaluation_span.set_attribute('app.evaluation.issue_count', len(result['issues']))
                    current_app.extensions['demo_metrics']['quality'].add(
                        1, dimensions(result='passed' if result['passed'] else 'failed'))
                    log_event('trip_evaluated', **{'app.evaluation.passed': result['passed'],
                                                 'app.evaluation.issue_count': len(result['issues'])})
                span.set_attribute('app.trip.valid', result['passed'])
                record_outcome(span, 'success' if result['passed'] else 'quality_rejected')
                # Technical completion is distinct from a product-contract rejection.
                return respond({**plan_payload(run, trip), 'evaluation': result,
                                'travel_plan': candidate_text, 'candidate': candidate, 'contract': contract,
                                'provenance': provenance, **original},
                               status=200 if result['passed'] else 422)
            except InputError as error:
                return reject_input(span, error)
            except Exception as error:
                return technical_failure(span, error)

    return app


app = create_app()
if __name__ == '__main__':
    start(app, 5003)

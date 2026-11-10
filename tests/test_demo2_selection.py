"""Demo 2 v1.1 selection regressions; no real model or backend calls.

The live-path doubles represent a completed model operation. They let these
tests distinguish selection after generation from skipping generation.
"""
from copy import deepcopy
from datetime import date, timedelta
from html.parser import HTMLParser
import importlib
import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from werkzeug.datastructures import MultiDict

import demo_common as common


class _Form(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.action = None
        self.fields = []
        self._textarea = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'form' and attrs.get('id') == 'request-form':
            self.action = attrs.get('action')
        elif tag == 'input' and attrs.get('name'):
            if attrs.get('type') in {'checkbox', 'radio'} and 'checked' not in attrs:
                return
            self.fields.append((attrs['name'], attrs.get('value', '')))
        elif tag == 'textarea' and attrs.get('name'):
            self._textarea = [attrs['name'], '']

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == 'textarea' and self._textarea is not None:
            self.fields.append(tuple(self._textarea))
            self._textarea = None


@pytest.fixture
def make_app(monkeypatch):
    # Use existing test-owned/no-op providers, never start a remote exporter.
    monkeypatch.setattr(common, '_telemetry_configured', True)
    monkeypatch.setenv('ENABLE_CONSOLE_EXPORTERS', 'false')
    monkeypatch.setenv('ENABLE_SENSITIVE_DATA', 'false')
    monkeypatch.setenv('DEMO_ENGINE', 'live')
    module = importlib.import_module('web_app_demo2')

    def factory(engine='live'):
        monkeypatch.setenv('DEMO_ENGINE', engine)
        app = module.create_app()
        app.config.update(TESTING=True, SHOW_REASONING=True)
        return app

    return factory


def _payload(**overrides):
    result = dict(date=(date.today() + timedelta(days=14)).isoformat(), duration=3,
                  interests=['food', 'architecture'], special_requests='Indoor alternatives.',
                  delay_scale=0)
    result.update(overrides)
    return result


def _fixture(name):
    return json.loads((common.ROOT / 'fixtures' / name).read_text(encoding='utf-8'))


def _live_run(text=None, *, weather=None):
    return common.PlanRun(
        text=text if text is not None else json.dumps(_fixture('good-plan.json')),
        reasoning=['Summary returned by the original model.'],
        evidence={'destination': 'Porto',
                  'weather': deepcopy(weather or _fixture('contract.json')['weather']),
                  'datetime': '2026-11-10T12:00:00+00:00'},
        engine='live',
    )


def _planner(app, run=None):
    planner = AsyncMock(return_value=run or _live_run())
    app.config['PLANNER'] = planner
    return planner


def _assert_live_substitution(data, original):
    provenance = data['provenance']
    assert provenance['engine'] == 'live'
    assert provenance['fixture'] == 'bad'
    assert provenance['candidate_source'] == 'bad_fixture_after_live_model'
    assert provenance['output_substituted'] is True
    assert provenance['fixture_path'] == 'fixtures/bad-plan.json'
    assert data['original_model_output'] == original.text
    assert data['reasoning'] == original.reasoning
    assert data['candidate'] == _fixture('bad-plan.json')
    assert data['contract']['weather'] == original.evidence['weather']
    assert data['evaluation']['passed'] is False
    assert data['evaluation']['issues']
    # The report identifies the evaluated candidate, not the original output.
    assert data['evaluation']['candidate_sha256']


def test_exact_bad_selector_forwards_in_action_and_hidden_fields(make_app):
    app = make_app()
    original = _live_run()
    planner = _planner(app, original)
    with app.test_client() as client:
        page = client.get('/?fixture=bad&delay_scale=0&unknown=do-not-forward')
        assert page.status_code == 200
        form = _Form()
        form.feed(page.get_data(as_text=True))
        target = urlsplit(form.action)
        assert target.path == '/plan'
        query = parse_qs(target.query)
        assert query['fixture'] == ['bad']
        assert len(query['delay_scale']) == 1
        assert float(query['delay_scale'][0]) == 0
        assert 'unknown' not in query
        posted = MultiDict(form.fields)
        assert posted['fixture'] == 'bad'
        assert float(posted['delay_scale']) == 0
        response = client.post(form.action, data=posted, headers={'Accept': 'application/json'})
    assert response.status_code == 422
    planner.assert_awaited_once()
    _assert_live_substitution(response.get_json(), original)


def test_query_fallback_survives_missing_hidden_fields(make_app):
    app = make_app()
    original = _live_run()
    planner = _planner(app, original)
    form = MultiDict(_payload().items())
    # Repeated fields are what a browser sends for the two checkboxes.
    form.setlist('interests', ['food', 'architecture'])
    form.pop('delay_scale')
    with app.test_client() as client:
        response = client.post('/plan?fixture=bad&delay_scale=0', data=form,
                               headers={'Accept': 'application/json'})
    assert response.status_code == 422
    planner.assert_awaited_once()
    _assert_live_substitution(response.get_json(), original)


@pytest.mark.parametrize('body_kind', ['json', 'form'])
@pytest.mark.parametrize('body_fixture,query_fixture,expected', [
    ('bad', 'good', 422), ('good', 'bad', 200),
])
def test_posted_selector_wins_over_query(make_app, body_kind, body_fixture, query_fixture, expected):
    app = make_app()
    original = _live_run()
    planner = _planner(app, original)
    values = _payload(fixture=body_fixture)
    kwargs = {'json': values} if body_kind == 'json' else {'data': values}
    with app.test_client() as client:
        response = client.post(f'/plan?fixture={query_fixture}',
                               headers={'Accept': 'application/json'}, **kwargs)
    assert response.status_code == expected
    planner.assert_awaited_once()
    data = response.get_json()
    if body_fixture == 'bad':
        _assert_live_substitution(data, original)
    else:
        assert data['candidate'] == json.loads(original.text)
        assert data['provenance']['output_substituted'] is False


def test_json_body_controls_win_but_query_supplies_missing_selector(make_app):
    app = make_app()
    captured = {}

    async def planner(*args, **kwargs):
        captured.update(common.chaos_config.get())
        return _live_run()

    app.config['PLANNER'] = planner
    with app.test_client() as client:
        response = client.post('/plan?fixture=bad&delay_scale=4&weather_delay=9',
                               json=_payload(delay_scale=0))
    assert response.status_code == 422
    assert captured['delay_scale'] == 0
    assert captured['weather_delay'] == 9


@pytest.mark.parametrize('engine', ['live', 'fixture'])
@pytest.mark.parametrize('selector', ['unknown', '', None, [], {}, ['bad'], True, 1])
def test_invalid_selectors_are_400_before_planner(make_app, engine, selector):
    app = make_app(engine)
    planner = _planner(app)
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture=selector))
    assert response.status_code == 400
    planner.assert_not_awaited()


def test_bad_substitution_preserves_unparseable_original_output(make_app):
    app = make_app()
    original = _live_run('The model did not return JSON. original-marker-71')
    planner = _planner(app, original)
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture='bad'))
    assert response.status_code == 422
    planner.assert_awaited_once()
    data = response.get_json()
    _assert_live_substitution(data, original)
    assert data['original_model_candidate'] is None


def test_bad_substitution_preserves_parseable_original_candidate(make_app):
    app = make_app()
    original = _live_run()
    _planner(app, original)
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture='bad'))
    data = response.get_json()
    assert response.status_code == 422
    assert data['original_model_candidate'] == json.loads(original.text)
    assert data['original_model_candidate'] != data['candidate']


@pytest.mark.parametrize('selector', [None, 'good'])
@pytest.mark.parametrize('candidate_name,expected', [('good-plan.json', 200), ('bad-plan.json', 422)])
def test_live_default_and_good_evaluate_actual_model_output(make_app, selector, candidate_name, expected):
    app = make_app()
    original = _live_run(json.dumps(_fixture(candidate_name)))
    planner = _planner(app, original)
    values = _payload()
    if selector is not None:
        values['fixture'] = selector
    with app.test_client() as client:
        response = client.post('/plan', json=values)
    assert response.status_code == expected
    planner.assert_awaited_once()
    data = response.get_json()
    assert data['candidate'] == json.loads(original.text)
    assert data['travel_plan'] == original.text
    assert data['provenance']['output_substituted'] is False
    assert data['evaluation']['passed'] is (expected == 200)


def test_bad_selector_does_not_mask_provider_failure(make_app):
    app = make_app()
    planner = AsyncMock(side_effect=RuntimeError('synthetic provider failure'))
    app.config['PLANNER'] = planner
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture='bad'))
    assert response.status_code == 502
    planner.assert_awaited_once()
    assert not response.get_json().get('evaluation', {}).get('passed', False)
    assert response.get_json().get('candidate') is None


def test_bad_fixture_fails_even_for_short_food_only_trip(make_app):
    app = make_app()
    original = _live_run()
    planner = _planner(app, original)
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture='bad', duration=1, interests=['food']))
    assert response.status_code == 422
    planner.assert_awaited_once()
    _assert_live_substitution(response.get_json(), original)


def test_fixture_mode_bad_never_creates_live_client(make_app, monkeypatch):
    app = make_app('fixture')
    factory = AsyncMock(side_effect=AssertionError('Fixture mode created a live client'))
    monkeypatch.setattr(common, 'make_chat_client', factory)
    with app.test_client() as client:
        response = client.post('/plan', json=_payload(fixture='bad'))
    assert response.status_code == 422
    assert response.get_json()['evaluation']['passed'] is False
    assert response.get_json()['candidate'] == _fixture('bad-plan.json')
    factory.assert_not_called()


def test_pack_version_is_visible_on_health_and_plan_responses(make_app):
    app = make_app()
    _planner(app)
    with app.test_client() as client:
        health = client.get('/health')
        response = client.post('/plan', json=_payload(fixture='bad'))
    assert health.get_json()['pack_version'] == '1.1.0'
    assert health.headers['X-Demo-Pack-Version'] == '1.1.0'
    assert response.headers['X-Demo-Pack-Version'] == '1.1.0'


def test_html_discloses_substitution_and_preserves_original_model_answer(make_app):
    app = make_app()
    candidate = _fixture('good-plan.json')
    candidate['indoor_alternative'] += ' original-live-marker-82'
    original = _live_run(json.dumps(candidate))
    _planner(app, original)
    with app.test_client() as client:
        response = client.post('/plan', data=_payload(fixture='bad'))
    assert response.status_code == 422
    page = response.get_data(as_text=True).casefold()
    assert 'bad fixture' in page
    assert 'original' in page and 'model' in page
    assert 'original-live-marker-82' in page

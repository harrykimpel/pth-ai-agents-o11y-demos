"""Demo 1: request -> agent/model/tool trace -> slow or unavailable weather.

Run: python web_app_demo1.py (http://127.0.0.1:5002)
"""
from flask import current_app
from demo_common import (InputError, create_base_app, execute_planner, parse_trip,
                         plan_payload, record_outcome, reject_input, request_scope,
                         respond, start, technical_failure)


def create_app():
    app = create_base_app('1', 'Follow the slow itinerary')

    @app.post('/plan')
    async def plan_trip():
        with request_scope() as span:
            try:
                trip = parse_trip()
                span.set_attribute('app.trip.duration_days', trip.duration)
                run = await execute_planner(trip)
                record_outcome(span, 'success')
                return respond(plan_payload(run, trip))
            except InputError as error:
                return reject_input(span, error)
            except Exception as error:
                return technical_failure(span, error)

    return app


app = create_app()
if __name__ == '__main__':
    start(app, 5002)

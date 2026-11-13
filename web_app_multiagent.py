"""Launch one of the Porto demos with Destination → Conditions → Itinerary.

python web_app_multiagent.py --demo 2  # http://127.0.0.1:5005
DEMO_ENGINE=fixture works without model credentials; live uses your normal .env.
"""
from __future__ import annotations

import argparse
from importlib import import_module


def create_app(demo='2'):
    demo = str(demo)
    if demo not in {'1', '2', '3'}:
        raise ValueError('Demo must be 1, 2 or 3.')
    app = import_module(f'web_app_demo{demo}').create_app()
    app.config['DEMO_WORKFLOW'] = 'multi'
    return app


if __name__ == '__main__':
    from demo_common import start

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', choices=['1', '2', '3'], default='2',
                        help='1: trace, 2: evaluate, 3: enforce (default: 2).')
    args = parser.parse_args()
    start(create_app(args.demo), 5005)

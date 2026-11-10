import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_downloaded_bundle_roundtrips_into_real_gate(tmp_path):
    bundle = dict(candidate=json.loads((ROOT / 'fixtures/good-plan.json').read_text()),
                  contract=json.loads((ROOT / 'fixtures/contract.json').read_text()))
    source = tmp_path / 'run.json'; source.write_text(json.dumps(bundle))
    dest = tmp_path / 'export'
    r = subprocess.run([sys.executable, str(ROOT / 'export_run.py'), str(source), '--out', str(dest)], capture_output=True)
    assert r.returncode == 0
    r = subprocess.run([sys.executable, str(ROOT / 'release_gate.py'), '--candidate', str(dest / 'candidate.json'),
                        '--contract', str(dest / 'contract.json')], capture_output=True)
    assert r.returncode == 0


def test_unparsed_candidate_cannot_be_exported_as_passable(tmp_path):
    source = tmp_path / 'run.json'; source.write_text(json.dumps({'candidate': None, 'contract': {}}))
    r = subprocess.run([sys.executable, str(ROOT / 'export_run.py'), str(source), '--out', str(tmp_path / 'export')], capture_output=True)
    assert r.returncode == 2

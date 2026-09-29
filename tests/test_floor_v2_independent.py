"""Separate checker challenged by the preregistered expected examples."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('independent',ROOT/'scripts/check_floor_v2.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
spec=importlib.util.spec_from_file_location('expected_cases',ROOT/'tests/test_floor_v2.py')
expected=importlib.util.module_from_spec(spec);spec.loader.exec_module(expected)
CASES=expected.test_scoring_adversaries.pytestmark[0].args[1]

@pytest.mark.parametrize('text,answer,kind',CASES)
def test_independent_parser(text,answer,kind):
    assert checker.independent_parse(text,'4 + 9')==(answer,kind)

runner_env=expected.runner_env


def test_passing_gate_freezes_evaluation_inputs_before_generation(runner_env):
    from typo_math_audit import floor_v2 as v2
    from typo_math_audit.common import read_json,file_hash
    p=runner_env
    assert expected.invoke(p/'pilot')==0
    assert expected.invoke(p/'final',phase='eval',pilot=p/'pilot',limit=7)==2
    config=read_json(p/'final/run.json')
    spec=config['specification']
    assert spec['selected']=='integer'
    assert spec['runtime_budget_seconds']==10800
    assert spec['pilot_evidence']['outputs_sha256']==file_hash(p/'pilot/outputs.jsonl')
    assert spec['cases_sha256']==file_hash(p/'final/cases.jsonl')
    assert v2.audit(p/'final',True)['records']==7

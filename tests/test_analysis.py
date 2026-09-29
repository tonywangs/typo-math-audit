import pytest
from typo_math_audit.analysis import summarize
from typo_math_audit.perturb import CONDITIONS


def records(values):
    result=[]
    for i,(clean,noisy) in enumerate(values):
        for c in CONDITIONS:
            result.append(dict(question_id=str(i),condition=c,family='addition',
                correct=clean if c=='clean' else noisy,status='valid',truncated=False,
                unchanged=c=='clean',possible_meaning_change=c!='clean',
                realized_eligible_word_rate=0,realized_all_word_rate=0,
                input_tokens=10,output_tokens=2,elapsed_seconds=1))
    return result


def test_known_paired_cells_and_zero_delta_interval():
    s=summarize(records([(1,1),(1,0),(0,1),(0,0)]),replicates=100)
    m=s['conditions']['delete-20']
    assert (m['both_correct'],m['clean_correct_to_incorrect'],m['clean_incorrect_to_correct'],m['both_incorrect'])==(1,1,1,1)
    assert m['paired_delta']==0 and m['accuracy']==.5
    assert m['break_rate_given_clean_correct']==.5
    assert s['conditions']['clean']['paired_delta_ci95']==[0,0]
    assert s==summarize(records([(1,1),(1,0),(0,1),(0,0)]),replicates=100)


def test_all_failure_and_all_success_have_honest_denominators():
    s=summarize(records([(0,0)]*6),replicates=100)['conditions']['keyboard-40']
    assert s['break_rate_given_clean_correct'] is None
    assert s['break_rate_ci95']==[None,None]
    assert s['bootstrap_zero_clean_correct_replicates']==100
    s=summarize(records([(1,0)]*6),replicates=100)['conditions']['keyboard-40']
    assert s['paired_delta_ci95']==[-1,-1]
    assert s['clean_correct_to_incorrect']==6
    assert s['denominator']==6


def test_duplicates_and_empty_fail():
    rows=records([(1,1)])
    with pytest.raises(ValueError): summarize(rows+[rows[0]])
    with pytest.raises(ValueError): summarize([])

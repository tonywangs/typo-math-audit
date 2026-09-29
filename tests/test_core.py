import copy
import itertools
import re
import pytest
from typo_math_audit.common import canonical, digest, seal, check_seal
from typo_math_audit.dataset import generate, oracle, FAMILIES
from typo_math_audit.perturb import cases, perturb, apply_edits, EDITABLE, KEYBOARD, KINDS
from typo_math_audit.scoring import score


def test_oracle_all_operands():
    for a,b in itertools.product(range(21), repeat=2):
        assert oracle("addition",a,b)==a+b
        assert oracle("multiplication",a,b)==a*b
        if a>=b:
            assert oracle("subtraction",a,b)==a-b


def test_split_counts_uniqueness_disjoint_replay():
    dev,ev=generate("dev"),generate("eval")
    assert dev==generate("dev") and ev==generate("eval")
    assert len(dev)==30 and len(ev)==210
    sig=lambda q:(q['family'],tuple(sorted(q['operands'])))
    assert not set(map(sig,dev)) & set(map(sig,ev))
    assert len(set(map(sig,dev+ev)))==240
    assert len({q['prompt'] for q in dev+ev})==240
    for family in FAMILIES:
        assert sum(q['family']==family for q in ev)==70
    assert all(q['answer']==q['oracle_answer'] for q in dev+ev)
    with pytest.raises(ValueError): generate('bad')


def test_all_edits_are_legal_nested_and_protect_semantics():
    for q in generate('dev')+generate('eval'):
        variants=list(cases([q]))
        assert len(variants)==7
        for c in variants:
            assert c['prompt']==apply_edits(q['prompt'],c['edits'])
            assert c['prompt'].split('\n')[1:]==q['prompt'].split('\n')[1:]
            assert re.findall(r'\d+',c['prompt'])==re.findall(r'\d+',q['prompt'])
            assert c['prompt_sha256']==digest(c['prompt'])
            assert c['eligible_words']==5
            assert c['changed_words']==len(c['edits'])
            assert c['unchanged']==(c['condition']=='clean')
            for e in c['edits']:
                assert e['original_word'].lower() in EDITABLE
                assert q['prompt'][e['word_start']:e['word_end']]==e['original_word']
                assert e['word_start']<=e['start']<e['end']<=e['word_end']
                if c['condition'].startswith('transpose'):
                    assert e['after']==e['before'][::-1] and e['after']!=e['before']
                elif c['condition'].startswith('delete'):
                    assert len(e['before'])==1 and e['after']==''
                else:
                    assert e['after'].lower() in KEYBOARD[e['before'].lower()]
        for kind in KINDS:
            low,high=perturb(q,kind,.2),perturb(q,kind,.4)
            assert low['changed_words']==1 and high['changed_words']==2
            assert low['realized_eligible_word_rate']==.2
            assert high['realized_eligible_word_rate']==.4
            assert all(e in high['edits'] for e in low['edits'])
            assert high==perturb(q,kind,.4)


def test_no_eligible_words_and_names_protected():
    q=dict(question_id='edge',family='addition',answer=3,prompt='Tony has 1 + 2. Reply with only the integer answer.')
    for kind in KINDS:
        r=perturb(q,kind,.4)
        assert r['unchanged'] and r['realized_eligible_word_rate']==0
        assert r['prompt']==q['prompt']


@pytest.mark.parametrize('text,parsed,valid', [(' 42\n',42,True),('+42',42,True),('-3',-3,True),('0042',42,True),('42.',None,False),('answer: 42',None,False),('4 2',None,False),('42\n43',None,False),('4.2e1',None,False),('',None,False),('４２',None,False),('42<eos>',None,False)])
def test_parser(text,parsed,valid):
    got=score(text,42)
    assert got['parsed_answer']==parsed
    assert (got['status']=='valid')==valid
    assert got['correct']==(valid and parsed==42)
    assert not score(text,42,True)['correct']


def test_tampering_detected():
    row=seal({'answer':3})
    check_seal(row)
    row['answer']=4
    with pytest.raises(ValueError): check_seal(row)


def test_bad_edits_rejected():
    with pytest.raises(ValueError):
        apply_edits('abc',[dict(start=0,end=1,before='z',after='q')])


def test_rendered_arithmetic_matches_oracle():
    from decimal import Decimal
    expected_symbols={'addition':'+','subtraction':'-','multiplication':'*'}
    for q in generate('dev')+generate('eval'):
        a,op,b=q['prompt'].splitlines()[1].split()
        assert op==expected_symbols[q['family']]
        assert [int(a),int(b)]==q['operands']
        operations={'+':lambda x,y:x+y,'-':lambda x,y:x-y,'*':lambda x,y:x*y}
        assert operations[op](Decimal(a),Decimal(b))==q['answer']

from src.strategies import evaluate_matrix

def pick(rows,name):
    return next(x for x in rows if x.strategy==name)

def test_matrix_has_24_strategies():
    assert len(evaluate_matrix(1500,0.015))==24

def test_small_build_is_still_tested_by_zero_threshold():
    rows=evaluate_matrix(10,0.005)
    assert pick(rows,"S0_SLIP1c").action=="COPY"
    assert pick(rows,"S500_SLIP1c").reason=="below_size_threshold"

def test_same_build_can_copy_under_loose_slippage_and_skip_strict():
    rows=evaluate_matrix(2500,0.025)
    assert pick(rows,"S2000_SLIP2c").action=="SKIP"
    assert pick(rows,"S2000_SLIP3c").action=="COPY"

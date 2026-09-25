from dataclasses import dataclass

SIZE_THRESHOLDS=(0,500,1000,2000,5000,10000)
SLIPPAGE_LIMITS=(0.01,0.02,0.03,0.05)

@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    min_build_usd: float
    max_slippage: float
    action: str
    reason: str
    simulated_size: float


def evaluate_matrix(build_usd,slippage,base_trade=50,fill_count=None):
    results=[]
    for minimum in SIZE_THRESHOLDS:
        for limit in SLIPPAGE_LIMITS:
            name="S{}_SLIP{}c".format(int(minimum),int(round(limit*100)))
            if build_usd < minimum:
                results.append(StrategyResult(name,minimum,limit,"SKIP","below_size_threshold",0.0))
            elif slippage is None:
                results.append(StrategyResult(name,minimum,limit,"SKIP","empty_order_book",0.0))
            elif slippage > limit:
                results.append(StrategyResult(name,minimum,limit,"SKIP","price_moved",0.0))
            elif slippage < 0:
                results.append(StrategyResult(name,minimum,limit,"COPY","price_improved",float(base_trade)))
            else:
                results.append(StrategyResult(name,minimum,limit,"COPY","paper_fill",float(base_trade)))
    # Experimental forward-only strategy discovered from historical RN1 analysis.
    # Keep it separate from the 24-strategy matrix so future results provide an
    # honest out-of-sample check rather than rewriting historical paper trades.
    name="S500_SLIP1c_F2_9"
    if build_usd < 500:
        results.append(StrategyResult(name,500,0.01,"SKIP","below_size_threshold",0.0))
    elif fill_count is None or not (2 <= int(fill_count) <= 9):
        results.append(StrategyResult(name,500,0.01,"SKIP","fill_count_outside_2_9",0.0))
    elif slippage is None:
        results.append(StrategyResult(name,500,0.01,"SKIP","empty_order_book",0.0))
    elif slippage > 0.01:
        results.append(StrategyResult(name,500,0.01,"SKIP","price_moved",0.0))
    elif slippage < 0:
        results.append(StrategyResult(name,500,0.01,"COPY","price_improved_f2_9",float(base_trade)))
    else:
        results.append(StrategyResult(name,500,0.01,"COPY","paper_fill_f2_9",float(base_trade)))
    return results

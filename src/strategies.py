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


def evaluate_matrix(build_usd,slippage,base_trade=50):
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
            else:
                results.append(StrategyResult(name,minimum,limit,"COPY","paper_fill",float(base_trade)))
    return results

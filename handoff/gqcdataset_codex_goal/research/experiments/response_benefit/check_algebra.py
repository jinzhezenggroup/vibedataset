"""Exercise the actual bounded planner without orbital integrals or a cluster."""
from itertools import combinations
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4] / 'scripts'))
from plans import ALL, HISTORIES, SCENARIOS, compile_plan


def main():
    # A basis of nine scalar tables independently exercises every coefficient.
    tests = 0
    for scenario, (mask, requests) in SCENARIOS.items():
        declared = HISTORIES[mask]
        for size in range(len(declared) + 1):
            for history in combinations(declared, size):
                for method in ('single', 'two', 'multi', 'hand_field', 'hand_adjoint', 'direct', 'adjoint'):
                    cols, answers = compile_plan(method, requests, history, ())
                    assert set(requests) == {(f,o) for f,o,_ in answers}
                    for unit in ALL:
                        for f, o, terms in answers:
                            total = 0.
                            for c, p, w in terms:
                                if c.startswith('H:'):
                                    pair = (c[2:], p)
                                    assert pair in history
                                    total += w * (unit == pair)
                                elif c in ('q0','r2','zz'):
                                    total += w * (unit == (p,c))
                                else:
                                    total += w * (unit[1] == p and unit[0] in c)
                            assert total == float((f,o) == unit)
                        tests += 1
                    if method == 'two' and scenario == 'cycle-three' and len(history) == 3:
                        assert cols == ('xy', 'yz')
                    if method == 'multi' and scenario == 'cycle-three' and len(history) == 3:
                        assert cols == ('xy', 'yz')
                    if method == 'single' and scenario == 'cycle-three' and len(history) == 3:
                        assert len(cols) == 3
    print(tests, 'basis tables under full and partial observed histories')


if __name__ == '__main__':
    main()

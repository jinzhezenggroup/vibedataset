"""An exact bound for the real system whose coefficients are the supplied binary64 values."""
from fractions import Fraction
from math import isqrt
from struct import iter_unpack


TOLERANCE = Fraction(1, 10**8)


def exact_bound(payload):
    # Layout is row-major A, b, w, candidate x, and its actual FP64 readout q.
    values = [Fraction.from_float(v) for (v,) in iter_unpack('<d', payload)]
    n = (isqrt(4 * len(values) + 5) - 3) // 2
    if n < 1 or n*n + 3*n + 1 != len(values):
        raise ValueError('unexpected binary matrix/vector dimensions')
    start = n*n
    b = values[start:start+n]
    w = values[start+n:start+2*n]
    x = values[start+2*n:-1]
    a = [values[i:i+n] for i in range(0, start, n)]
    margins = [2 * abs(row[i]) - sum(map(abs, row)) for i, row in enumerate(a)]
    delta = min(margins)
    result = {'dimension': n, 'minimum_margin': str(delta), 'worst_row': margins.index(delta),
              'nondominant_rows': sum(v <= 0 for v in margins)}
    if delta <= 0:
        return dict(result, status='evidence_unavailable')
    residual = max(abs(value - sum(c * u for c, u in zip(row, x))) for value, row in zip(b, a))
    exact_dot = sum(c * u for c, u in zip(w, x))
    rounding = abs(exact_dot - values[-1])
    bound = sum(map(abs, w)) * residual / delta + rounding
    return dict(result, status='accepted' if bound <= TOLERANCE else 'refine',
                residual_inf=str(residual), readout_roundoff=str(rounding), absolute_bound=str(bound))

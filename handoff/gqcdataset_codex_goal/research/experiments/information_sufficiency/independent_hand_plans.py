"""Independent hand-written field formulas for the #25 control."""

FIELDS = ("x", "y", "z")
OBS = ("q0", "r2", "zz")
SINGLE = tuple(zip(FIELDS, OBS))
CYCLE = (("y", "q0"), ("z", "r2"), ("x", "zz"))
CROSS = (("y", "q0"), ("x", "r2"))


def ordinary(requests, orientation):
    rows = []
    for field, observable in requests:
        if orientation == "field":
            rows.append((field, observable, ((field, observable, 1),)))
        else:
            rows.append((field, observable, ((observable, field, 1),)))
    return tuple(sorted({term[0] for _, _, terms in rows for term in terms})), tuple(rows)


def plan(requests, known, orientation):
    requests = tuple(requests)
    known = set(known)
    if len(requests) == 1 or not set(CYCLE).issubset(known):
        return ordinary(requests, orientation)
    if requests == SINGLE:
        # U=x+y and V=y+z are written directly here.  This module does not
        # import the candidate planner or inspect any target reference.
        rows = (
            ("x", "q0", (("xy", "q0", 1), ("H:y", "q0", -1))),
            ("y", "r2", (("yz", "r2", 1), ("H:z", "r2", -1))),
            ("z", "zz", (("xy", "zz", -1), ("yz", "zz", 1), ("H:x", "zz", 1))),
        )
        return ("xy", "yz"), rows
    return ordinary(requests, orientation)

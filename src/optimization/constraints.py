"""Constraint building blocks (vehicle capacity, depot/centre assignment,
driver shift limits, minimum headway). See docs/optimization_problem.md.

Not implemented yet: driver shift/availability constraints in particular
are NOT FEASIBLE with current data — no driver availability or working-
hours collection was found during discovery (see docs/database.md,
section G — Drivers). NamesConv only maps a driver code to a name/phone,
with no schedule or availability. This must be re-scoped or new data
must be collected before driver-aware scheduling can be built.
"""

# The SKILL's rule, DEMONSTRATED BY A FAILING CASE

`expected.json` links properly: `[[dec-ocheredi]]`.

`counterexample.json` is byte-identical except that the body cites a BARE ID:
`"Это отменяет DEC-004."`

On cybos that bare ID matches the layout's `id-ref` regex, so it CREATES A REF — and
`dec-004` is not a page. `apply` refuses the batch with `UNRESOLVED_REF`.

The test feeds BOTH through the real validators: the expected one passes, the
counterexample is refused. The SKILL's rule is thereby demonstrated, not merely asserted
— a doc rule with no failing case is a doc rule that rots.

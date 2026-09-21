# The law of ADRs

**A stable ADR is settled.** `status: stable` records a decision the user has vetted. Change one only when the user has explicitly asked for that change to that ADR. A decision that has moved on gets a **new** ADR, retired against the old one with `vaultwright supersede`, so the original keeps saying what was decided and why. A `draft` ADR is still open, and can be edited as the discussion goes.

**Writing one.** `/domain-modeling` writes ADRs in its own format. Give each one frontmatter with vaultwright (see `../CLAUDE.md`): `type: adr`, and a status mapped from the ADR's own — proposed → `draft`, accepted → `stable`. Number it one past the highest here, and add it to `index.md`.

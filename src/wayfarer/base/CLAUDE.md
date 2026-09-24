# Running tests

Run every test through `wf-test`: `wf-test` alone runs this repo's suite, and
`wf-test <command>` runs the command you give it, such as one test file. It exits
with the tests' own status and prints one line of its own last. Keep that line:
do not pipe `wf-test` through anything that drops its last line.

# Asking

Ask a person only for an open decision that changes what the code visibly does,
and that the ticket, its parent spec and the code do not settle. Otherwise
proceed, and record what you decided as an assumption. A ticket with no agreed
seam is not a question: choose one and record it as an assumption.

Ask with `AskUserQuestion`, as the only tool call in its turn. The session ends
there, and nobody can answer until it has: when the answer comes, the session
resumes where it asked.

# Running tests

Run every test through `wf-test`: `wf-test` alone runs this repo's suite, and
`wf-test <command>` runs the command you give it, such as one test file. It exits
with the tests' own status and prints one line of its own last. Keep that line:
do not pipe `wf-test` through anything that drops its last line.

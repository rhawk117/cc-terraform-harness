---
type: llm
focus: last_message
---

PASS if the final message asks the user both start questions, in any wording: which findings to fix, offering three choices (the Critical and High findings as the recommended choice, all findings, or pick by ID), and whether to commit per finding or leave the changes uncommitted.
FAIL if the message proposes or makes fixes without asking, or asks only one of the two questions.

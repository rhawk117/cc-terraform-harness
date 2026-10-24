---
type: regex
target: trace
pattern: '^(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_instance\.worker\[0\](?:\\n|\s)*to\s*=\s*aws_instance\.worker\[\\*"ingest\\*"\])(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_instance\.worker\[1\](?:\\n|\s)*to\s*=\s*aws_instance\.worker\[\\*"transform\\*"\])(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_instance\.worker\[2\](?:\\n|\s)*to\s*=\s*aws_instance\.worker\[\\*"publish\\*"\])'
---

Each counted instance moves to the key the user named: 0 to ingest, 1 to transform, 2 to publish.

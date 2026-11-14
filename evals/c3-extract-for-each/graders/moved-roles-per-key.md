---
type: regex
target: trace
pattern: '^(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role\.svc\[\\*"api\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"api\\*"\]\.aws_iam_role\.\w+)(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role\.svc\[\\*"worker\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"worker\\*"\]\.aws_iam_role\.\w+)(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role\.svc\[\\*"billing\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"billing\\*"\]\.aws_iam_role\.\w+)'
---

Each role moves by key: aws_iam_role.svc["api"|"worker"|"billing"] to module.X["same key"].aws_iam_role.

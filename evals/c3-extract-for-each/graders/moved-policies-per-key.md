---
type: regex
target: trace
pattern: '^(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role_policy\.svc\[\\*"api\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"api\\*"\]\.aws_iam_role_policy\.\w+)(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role_policy\.svc\[\\*"worker\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"worker\\*"\]\.aws_iam_role_policy\.\w+)(?=[\s\S]*moved\s*\{(?:\\n|\s)*from\s*=\s*aws_iam_role_policy\.svc\[\\*"billing\\*"\](?:\\n|\s)*to\s*=\s*module\.[\w-]+\[\\*"billing\\*"\]\.aws_iam_role_policy\.\w+)'
---

Each inline policy moves by key into the same module instance as its role.

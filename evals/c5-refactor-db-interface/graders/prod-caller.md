---
type: regex
target: {source: file, path: envs/prod/main.tf}
pattern: '^(?=[\s\S]*database\s*=\s*\{)(?=[\s\S]*"orders-prod")(?=[\s\S]*db\.r6g\.large)(?=[\s\S]*200)(?=[\s\S]*14)'
---

envs/prod passes database = { ... } with its identifier, class, storage and retention unchanged.

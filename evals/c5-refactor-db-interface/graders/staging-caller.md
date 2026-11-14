---
type: regex
target: {source: file, path: envs/staging/main.tf}
pattern: '^(?=[\s\S]*database\s*=\s*\{)(?=[\s\S]*"orders-staging")(?=[\s\S]*db\.t4g\.medium)(?=[\s\S]*50)(?=[\s\S]*7)'
---

envs/staging passes database = { ... } with its identifier, class, storage and retention unchanged.

---
type: regex
target: {source: file, path: envs/dev/queue.tf}
pattern: '^(?=[\s\S]*source\s*=\s*"\.\./\.\./modules/orders-queue")(?=[\s\S]*345600)(?=[\s\S]*=\s*10\s*\n)'
---

envs/dev/queue.tf calls the module with the dev retention (345600) and threshold (10).

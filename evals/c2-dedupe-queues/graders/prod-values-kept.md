---
type: regex
target: {source: file, path: envs/prod/queue.tf}
pattern: '^(?=[\s\S]*source\s*=\s*"\.\./\.\./modules/orders-queue")(?=[\s\S]*1209600)(?=[\s\S]*=\s*1\s*\n)'
---

envs/prod/queue.tf calls the module with the prod retention (1209600) and threshold (1).

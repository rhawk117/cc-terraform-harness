---
type: regex
target: {source: file, path: modules/storage/logs.tf}
pattern: 'resource\s+"aws_s3_bucket_public_access_block"'
---

The log bucket blocks public access with its own public access block resource.

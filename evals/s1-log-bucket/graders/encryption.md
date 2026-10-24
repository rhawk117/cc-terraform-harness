---
type: regex
target: {source: file, path: modules/storage/logs.tf}
pattern: 'resource\s+"aws_s3_bucket_server_side_encryption_configuration"'
---

The log bucket is encrypted at rest through the split encryption resource.

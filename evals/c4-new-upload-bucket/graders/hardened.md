---
type: regex
target: {source: file, path: modules/upload-bucket/main.tf}
pattern: '^(?=[\s\S]*aws_s3_bucket_public_access_block)(?=[\s\S]*aws_s3_bucket_server_side_encryption_configuration)(?=[\s\S]*prevent_destroy\s*=\s*true)'
---

The bucket has a public access block, server-side encryption and prevent_destroy.

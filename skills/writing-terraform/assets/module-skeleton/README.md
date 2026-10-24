# data-bucket

Manages one S3 bucket for an application's data, hardened by default.

## Manages

- `aws_s3_bucket.data`, with `prevent_destroy`.
- A public access block, owner-enforced object ownership, KMS encryption with a bucket key, and versioning.

## Does not manage

- Lifecycle or retention rules. How long data is kept is the caller's decision, so the module sets none.
- Bucket policies, access logging and replication.
- The provider configuration. The calling root configures `aws`.

## Inputs

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `name_prefix` | `string` | yes | Prefix for every resource name, usually the application name. |
| `environment` | `string` | yes | `dev`, `staging` or `prod`, used in resource names. |

## Outputs

| Name | Description |
| --- | --- |
| `bucket_name` | Name of the data bucket. |
| `bucket_arn` | ARN of the data bucket, for IAM policies that grant access to it. |

## Tests

`terraform test` runs every case as a plan against a mocked provider, so nothing is created and no credentials are needed.

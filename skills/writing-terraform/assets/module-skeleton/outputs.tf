output "bucket_name" {
  description = "Name of the data bucket."
  value       = aws_s3_bucket.data.bucket
}

output "bucket_arn" {
  description = "ARN of the data bucket, for IAM policies that grant access to it."
  value       = aws_s3_bucket.data.arn
}

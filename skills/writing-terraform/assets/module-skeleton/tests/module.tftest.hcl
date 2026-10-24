mock_provider "aws" {}

variables {
  name_prefix = "orders"
  environment = "dev"
}

run "names_the_bucket_from_its_inputs" {
  command = plan

  assert {
    condition     = aws_s3_bucket.data.bucket == "orders-dev-data"
    error_message = "The bucket name must be <name_prefix>-<environment>-data."
  }
}

run "blocks_public_access" {
  command = plan

  assert {
    condition     = aws_s3_bucket_public_access_block.data.restrict_public_buckets
    error_message = "The public access block must restrict public buckets."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "qa"
  }

  expect_failures = [var.environment]
}

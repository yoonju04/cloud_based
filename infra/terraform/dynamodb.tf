# Conditional writes are the point of this table.
# UpdateItem must require version and, for commit, commit_count = 0.
# The leases_by_expiry index is how a sweeper would find expired leases.
# Active items set lease_pk = "active"; released items omit it.

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.name_prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "lease_pk"
    type = "S"
  }

  attribute {
    name = "lease_expires_at"
    type = "N"
  }

  global_secondary_index {
    name            = "leases_by_expiry"
    hash_key        = "lease_pk"
    range_key       = "lease_expires_at"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.name_prefix}-idempotency"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "packages" {
  name         = "${var.name_prefix}-packages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "package_id"

  attribute {
    name = "package_id"
    type = "S"
  }

  attribute {
    name = "content_hash"
    type = "S"
  }

  global_secondary_index {
    name            = "by_content_hash"
    hash_key        = "content_hash"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = true
  }
}

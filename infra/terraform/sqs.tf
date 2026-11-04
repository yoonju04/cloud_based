# At-least-once delivery. A second copy of the same message is expected.
# Consumers must send idempotency_key and the control plane must treat a
# repeated commit of that key as a no-op. Visibility timeout is not a
# substitute for that conditional write.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-work-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "work" {
  name                       = "${var.name_prefix}-work"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

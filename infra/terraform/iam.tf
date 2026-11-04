data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "batch_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["batch.amazonaws.com"]
    }
  }
}

# 123456789012 is the account id used in AWS documentation examples.
# It is not a target account and this role is not deployed.
data "aws_iam_policy_document" "proposal_operator_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::123456789012:root"]
    }
  }
}

resource "aws_iam_role" "control_plane" {
  name               = "${var.name_prefix}-control-plane"
  assume_role_policy = data.aws_iam_policy_document.proposal_operator_assume.json
  description        = "Proposal role for the validation control plane. Not deployed."
}

resource "aws_iam_role_policy" "control_plane" {
  name = "${var.name_prefix}-control-plane"
  role = aws_iam_role.control_plane.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "QueueSend"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:GetQueueUrl"]
        Resource = [aws_sqs_queue.work.arn]
      },
      {
        Sid    = "JobState"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.jobs.arn,
          "${aws_dynamodb_table.jobs.arn}/index/*",
          aws_dynamodb_table.idempotency.arn,
          aws_dynamodb_table.packages.arn,
          "${aws_dynamodb_table.packages.arn}/index/*",
        ]
      },
      {
        Sid      = "EvidenceWrite"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.evidence.arn}/packages/*", "${aws_s3_bucket.evidence.arn}/logs/*"]
      },
      {
        Sid      = "StartValidation"
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [aws_sfn_state_machine.validation.arn]
      }
    ]
  })
}

resource "aws_iam_role" "worker" {
  name               = "${var.name_prefix}-worker"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  description        = "Proposal role for a replay or SIL worker. Not deployed."
}

resource "aws_iam_role_policy" "worker" {
  name = "${var.name_prefix}-worker"
  role = aws_iam_role.worker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QueueConsume"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes",
        ]
        Resource = [aws_sqs_queue.work.arn]
      },
      {
        Sid      = "LogsWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = ["${aws_s3_bucket.evidence.arn}/logs/*"]
      },
      {
        Sid      = "ConditionalJobUpdate"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.jobs.arn]
      }
    ]
  })
}

resource "aws_iam_role" "auditor" {
  name               = "${var.name_prefix}-auditor"
  assume_role_policy = data.aws_iam_policy_document.proposal_operator_assume.json
  description        = "Read-only proposal role for a third party checking a package. Not deployed."
}

resource "aws_iam_role_policy" "auditor" {
  name = "${var.name_prefix}-auditor"
  role = aws_iam_role.auditor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadState"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.jobs.arn,
          aws_dynamodb_table.packages.arn,
          "${aws_dynamodb_table.packages.arn}/index/*",
        ]
      },
      {
        Sid      = "ReadEvidence"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.evidence.arn}/*"]
      }
    ]
  })
}

resource "aws_iam_role" "sfn" {
  name               = "${var.name_prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  description        = "Proposal role for the validation state machine. Not deployed."
}

resource "aws_iam_role_policy" "sfn" {
  name = "${var.name_prefix}-sfn"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ConditionalUpdates"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = [aws_dynamodb_table.jobs.arn, aws_dynamodb_table.idempotency.arn]
      },
      {
        Sid      = "Dispatch"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.work.arn]
      },
      {
        Sid    = "StateMachineLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.name_prefix}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  description        = "Proposal ECS execution role. The image is not published."
}

resource "aws_iam_role_policy" "ecs_execution" {
  name = "${var.name_prefix}-ecs-exec"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteWorkerLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.workers.arn}:*"]
      }
    ]
  })
}

resource "aws_iam_role" "batch_service" {
  name               = "${var.name_prefix}-batch"
  assume_role_policy = data.aws_iam_policy_document.batch_assume.json
  description        = "Proposal Batch service role. The job queue is DISABLED."
}

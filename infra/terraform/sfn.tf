resource "aws_sfn_state_machine" "validation" {
  name     = "${var.name_prefix}-validation"
  role_arn = aws_iam_role.sfn.arn

  definition = templatefile("${path.module}/statemachine.asl.json", {
    jobs_table     = aws_dynamodb_table.jobs.name
    work_queue_url = aws_sqs_queue.work.url
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }
}

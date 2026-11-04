# Log groups and one DLQ alarm.
# The alarm threshold is a design note. It is not an observed production alarm.

resource "aws_cloudwatch_log_group" "control_plane" {
  name              = "/fts/proposal/control-plane"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = "/fts/proposal/workers"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/fts/proposal/state-machine"
  retention_in_days = 14
}

resource "aws_cloudwatch_metric_alarm" "work_dlq" {
  alarm_name          = "${var.name_prefix}-work-dlq-not-empty"
  alarm_description   = "Proposal alarm: a work message reached the DLQ. Not an observed incident."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }
}

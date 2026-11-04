output "proposal_status" {
  value       = "not-deployed course sketch"
  description = "This stack is not a deployment. The string is a reminder in plan output, which the proposal guard refuses by default."
}

output "jobs_table_name" {
  value = aws_dynamodb_table.jobs.name
}

output "work_queue_name" {
  value = aws_sqs_queue.work.name
}

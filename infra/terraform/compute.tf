# Workers are sketched, not run.
# ECS desired_count is 0. The Batch queue is DISABLED.
# example.invalid is a reserved name; there is no image to pull.

resource "aws_ecs_cluster" "workers" {
  name = "${var.name_prefix}-workers"
}

resource "aws_ecs_task_definition" "replay" {
  family                   = "${var.name_prefix}-replay"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker.arn

  container_definitions = jsonencode([
    {
      name      = "replay"
      image     = "example.invalid/fts-replay:not-published"
      essential = true
      environment = [
        { name = "FTS_MODE", value = "proposal" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.workers.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "replay"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "replay" {
  name            = "${var.name_prefix}-replay"
  cluster         = aws_ecs_cluster.workers.id
  task_definition = aws_ecs_task_definition.replay.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.a.id, aws_subnet.c.id]
    security_groups  = [aws_security_group.workers.id]
    assign_public_ip = false
  }
}

resource "aws_batch_compute_environment" "sil" {
  compute_environment_name = "${var.name_prefix}-sil"
  type                     = "MANAGED"
  state                    = "ENABLED"
  service_role             = aws_iam_role.batch_service.arn

  compute_resources {
    type               = "FARGATE"
    max_vcpus          = 4
    subnets            = [aws_subnet.a.id, aws_subnet.c.id]
    security_group_ids = [aws_security_group.workers.id]
  }
}

resource "aws_batch_job_queue" "sil" {
  name     = "${var.name_prefix}-sil"
  state    = "DISABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.sil.arn
  }
}

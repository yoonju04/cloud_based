# Placeholder network so ECS and Batch references are self-contained.
# No NAT gateway and no VPC endpoints: this sketch is not meant to run tasks.

resource "aws_vpc" "proposal" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}-not-deployed"
  }
}

resource "aws_subnet" "a" {
  vpc_id            = aws_vpc.proposal.id
  cidr_block        = "10.42.1.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "${var.name_prefix}-a"
  }
}

resource "aws_subnet" "c" {
  vpc_id            = aws_vpc.proposal.id
  cidr_block        = "10.42.2.0/24"
  availability_zone = "${var.aws_region}c"

  tags = {
    Name = "${var.name_prefix}-c"
  }
}

resource "aws_security_group" "workers" {
  name        = "${var.name_prefix}-workers"
  description = "Proposal sketch for worker tasks. No inbound rules."
  vpc_id      = aws_vpc.proposal.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

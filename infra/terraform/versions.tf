# PROPOSAL SKETCH — NOT DEPLOYED.
# Do not apply this stack. It is a course design artifact, not a 42dot system.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project         = "fts-course-proposal"
      Status          = "not-deployed"
      Real42dotSystem = "false"
    }
  }
}

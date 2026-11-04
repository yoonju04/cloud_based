# The executable control plane is src/fts/jobs/control.py.
# These resources are the proposed cloud shape of that control plane.

resource "terraform_data" "proposal_guard" {
  input = "proposal-not-deployed"

  lifecycle {
    precondition {
      condition     = var.allow_apply
      error_message = "Refusing to plan or apply. This stack is a course proposal sketch, not a deployment and not a 42dot production system. Leave allow_apply false."
    }
  }
}

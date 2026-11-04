variable "aws_region" {
  type        = string
  default     = "ap-northeast-2"
  description = "Single control-plane region in this sketch. US engineers call it; a second region is not designed here."
}

variable "name_prefix" {
  type        = string
  default     = "fts-course-proposal"
  description = "Prefix for sketched resource names."
}

variable "evidence_bucket_name" {
  type        = string
  default     = "fts-course-proposal-evidence-not-deployed"
  description = "Placeholder bucket name. Do not apply; the name is not reserved by this repo."
}

variable "allow_apply" {
  type        = bool
  default     = false
  description = "Leave false. proposal_guard refuses plan and apply unless this is true, which is outside the assignment."
}

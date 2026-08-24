# SNS alerting for Ops Assistant (Alertmanager → SNS).
# Additive only: topic + optional email subscription + worker Publish permission.

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-${var.environment}-alerts"

  tags = {
    Name        = "${var.project_name}-${var.environment}-alerts"
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "aws_iam_policy_document" "workers_sns_alerts" {
  statement {
    sid    = "PublishOpsAssistantAlerts"
    effect = "Allow"
    actions = [
      "sns:Publish",
    ]
    resources = [
      aws_sns_topic.alerts.arn,
    ]
  }
}

resource "aws_iam_role_policy" "workers_sns_alerts" {
  name   = "${var.project_name}-${var.environment}-workers-sns-alerts"
  role   = module.k8s_cluster.worker_iam_role_name
  policy = data.aws_iam_policy_document.workers_sns_alerts.json
}

output "sns_alert_topic_arn" {
  description = "SNS topic ARN for Kubernetes / Alertmanager notifications"
  value       = aws_sns_topic.alerts.arn
}

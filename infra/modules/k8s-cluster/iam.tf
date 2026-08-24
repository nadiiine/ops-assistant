# IAM for kubeadm EC2 nodes.
#
# Baseline: separate control-plane / worker roles + instance profiles.
# Optional: AmazonSSMManagedInstanceCore (Session Manager).
# Bootstrap: least-privilege SSM Parameter Store access for the join command only.
#
# Intentionally NOT included:
#   - AmazonEKS* policies
#   - cloud-provider-aws / CCM policies
#   - Broad ssm:GetParametersByPath / ssm:* on all parameters
#
# ECR: workers get AmazonEC2ContainerRegistryReadOnly so they can pull
# ops-assistant images. This does not grant cluster-admin or EKS APIs.

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    sid     = "EC2AssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

################################################################################
# Control-plane
################################################################################

resource "aws_iam_role" "control_plane" {
  name               = "${local.name_prefix}-control-plane"
  description        = "IAM role for the kubeadm control-plane EC2 instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-control-plane-role"
    Role = "control-plane"
  })
}

resource "aws_iam_instance_profile" "control_plane" {
  name = "${local.name_prefix}-control-plane"
  role = aws_iam_role.control_plane.name

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-control-plane-profile"
    Role = "control-plane"
  })
}

resource "aws_iam_role_policy_attachment" "control_plane_ssm" {
  count = var.enable_ssm ? 1 : 0

  role       = aws_iam_role.control_plane.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "control_plane_join_ssm" {
  statement {
    sid    = "WriteKubeadmJoinParameter"
    effect = "Allow"
    actions = [
      "ssm:PutParameter",
      "ssm:GetParameter",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_join_parameter_name}",
    ]
  }
}

resource "aws_iam_role_policy" "control_plane_join_ssm" {
  name   = "${local.name_prefix}-control-plane-join-ssm"
  role   = aws_iam_role.control_plane.id
  policy = data.aws_iam_policy_document.control_plane_join_ssm.json
}

################################################################################
# Workers
################################################################################

resource "aws_iam_role" "workers" {
  name               = "${local.name_prefix}-workers"
  description        = "IAM role for kubeadm worker EC2 instances"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-workers-role"
    Role = "worker"
  })
}

resource "aws_iam_instance_profile" "workers" {
  name = "${local.name_prefix}-workers"
  role = aws_iam_role.workers.name

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-workers-profile"
    Role = "worker"
  })
}

resource "aws_iam_role_policy_attachment" "workers_ssm" {
  count = var.enable_ssm ? 1 : 0

  role       = aws_iam_role.workers.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "workers_join_ssm" {
  statement {
    sid    = "ReadKubeadmJoinParameter"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_join_parameter_name}",
    ]
  }
}

resource "aws_iam_role_policy" "workers_join_ssm" {
  name   = "${local.name_prefix}-workers-join-ssm"
  role   = aws_iam_role.workers.id
  policy = data.aws_iam_policy_document.workers_join_ssm.json
}

resource "aws_iam_role_policy_attachment" "workers_ecr" {
  role       = aws_iam_role.workers.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Minimal Bedrock inference for the in-cluster backend (uses the worker
# instance profile via the EC2 IMDS credential chain). Nova 2 Lite has no
# in-region on-demand ID in us-east-1; Converse must use the US geo inference
# profile, which may invoke the FM in us-east-1 / us-east-2 / us-west-2.
data "aws_iam_policy_document" "workers_bedrock" {
  statement {
    sid    = "BedrockConverseNova2Lite"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:inference-profile/us.amazon.nova-2-lite-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0",
      "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0",
      "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0",
    ]
  }
}

resource "aws_iam_role_policy" "workers_bedrock" {
  name   = "${local.name_prefix}-workers-bedrock"
  role   = aws_iam_role.workers.id
  policy = data.aws_iam_policy_document.workers_bedrock.json
}

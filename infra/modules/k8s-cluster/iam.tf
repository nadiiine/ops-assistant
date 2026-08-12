# IAM for future kubeadm EC2 nodes (no EC2 instances yet).
#
# Baseline: separate control-plane and worker roles + instance profiles.
# Optional AWS managed policy: AmazonSSMManagedInstanceCore (Session Manager).
#
# Intentionally NOT included (not required by current kubeadm architecture):
#   - AmazonEKS* policies (this is not EKS)
#   - ECR pull policies (no private registry in Phase 2 yet)
#   - cloud-provider-aws / CCM policies (not enabling AWS cloud-provider yet)
#   - S3, autoscaling, ELB admin, or any broad admin policies

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

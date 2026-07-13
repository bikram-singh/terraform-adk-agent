"""Resource planning for Terraform generation."""

from __future__ import annotations

from terraform_agent.intelligence.models import GCSRequest, ResourcePlan


def plan_gcs_project(request: GCSRequest) -> ResourcePlan:
    """Create an inspectable plan before rendering Terraform."""

    return ResourcePlan(
        service="gcs",
        workspace_name=request.workspace_name,
        resources=("google_storage_bucket.this",),
        generated_files=(
            "versions.tf",
            "providers.tf",
            "variables.tf",
            "main.tf",
            "outputs.tf",
            "terraform.tfvars.example",
            "README.md",
            "validation-report.md",
        ),
        security_controls=(
            "Uniform bucket-level access",
            "Public access prevention",
            "Object versioning",
            "force_destroy disabled",
            "No public IAM grants",
            "No embedded credentials",
        ),
        request=request.to_dict(),
    )

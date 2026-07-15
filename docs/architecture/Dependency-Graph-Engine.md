# Dependency Graph Engine

Version 0.9 converts high-level intent into a deterministic infrastructure
dependency graph.

Initial recipe:

- Private Cloud Run
- Cloud SQL
- VPC
- Subnet
- Private Service Access
- Serverless VPC Access connector
- Secret Manager
- Runtime service account
- IAM bindings

v0.9 is planning-only. It does not generate partial multi-service projects.
Complete generation is allowed only when every required graph node has an
available generator.

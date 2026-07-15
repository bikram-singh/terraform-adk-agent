"""Tests for the Pub/Sub generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("pubsub")
    values = {
        "region": "asia-south1",
        "topics": ["order-events"],
        "subscriptions": {
            "order-events-sub": {"topic": "order-events"},
        },
        "environment": "dev",
        "owner": "platform-team",
        "application": "orders-api",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-pubsub",
            values=values,
        )
    )


def test_pubsub_plugin_is_registered() -> None:
    assert "pubsub" in generator_registry.list_services()


def test_pubsub_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "subscriptions.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_pubsub_creates_topic_and_subscription() -> None:
    project = _project()
    assert "google_pubsub_topic" in project.files["main.tf"]
    assert "google_pubsub_subscription" in project.files["subscriptions.tf"]
    assert 'ttl = ""' in project.files["subscriptions.tf"]


def test_pubsub_rejects_subscription_with_unknown_topic() -> None:
    with pytest.raises(ValueError):
        _project(
            subscriptions={
                "bad-sub": {"topic": "does-not-exist"},
            }
        )


def test_pubsub_dead_letter_queue_generates_service_agent_bindings() -> None:
    project = _project(
        subscriptions={
            "order-events-sub": {
                "topic": "order-events",
                "enable_dead_letter": True,
            },
        }
    )
    assert 'resource "google_pubsub_topic" "dead_letter"' in project.files[
        "main.tf"
    ]
    iam_tf = project.files["iam.tf"]
    assert "dead_letter_publisher" in iam_tf
    assert "dead_letter_subscriber" in iam_tf
    assert "gcp-sa-pubsub.iam.gserviceaccount.com" in project.files[
        "main.tf"
    ]


def test_pubsub_least_privilege_iam_bindings() -> None:
    project = _project(
        publisher_members=[
            "serviceAccount:publisher@my-project.iam.gserviceaccount.com"
        ],
        subscriber_members=[
            "serviceAccount:subscriber@my-project.iam.gserviceaccount.com"
        ],
    )
    iam_tf = project.files["iam.tf"]
    assert "roles/pubsub.publisher" in iam_tf
    assert "roles/pubsub.subscriber" in iam_tf


def test_pubsub_rejects_empty_topics() -> None:
    with pytest.raises(ValueError):
        _project(topics=[])


def test_pubsub_rejects_duplicate_topics() -> None:
    with pytest.raises(ValueError):
        _project(topics=["dup", "dup"])


def test_pubsub_rejects_invalid_ack_deadline() -> None:
    with pytest.raises(ValueError):
        _project(
            subscriptions={
                "order-events-sub": {
                    "topic": "order-events",
                    "ack_deadline_seconds": 5000,
                },
            }
        )


def test_pubsub_rejects_public_publisher_member() -> None:
    with pytest.raises(ValueError):
        _project(publisher_members=["allUsers"])

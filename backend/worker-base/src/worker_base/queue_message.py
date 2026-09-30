#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
import logging
from typing import Any, Dict, List, Optional

import aio_pika
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class BaseMessage(BaseModel):
    job_id: str | None = Field(default=None, alias="job_id")
    workflow_id: str | None = Field(default=None, alias="workflow_id")
    local_file: str | None = Field(default=None, alias="local_file")

    async def write_message(self, channel, queue_name, ttl_seconds=None):
        body = self.model_dump(by_alias=True)
        message_kwargs = {
            "body": json.dumps(body).encode(),
            "delivery_mode": aio_pika.DeliveryMode.PERSISTENT,
        }
        if ttl_seconds is not None:
            message_kwargs["expiration"] = ttl_seconds
        await channel.default_exchange.publish(
            aio_pika.Message(**message_kwargs),
            routing_key=queue_name,
        )

    @classmethod
    def from_body(cls, message_body):
        return cls.model_validate_json(message_body)

    def dump_message(self):
        return json.dumps(self.model_dump(by_alias=True))


class BaseQueueMessage(BaseMessage):
    session_id: str = Field(alias="session_id")


class BaseTriggerMessage(BaseMessage):
    application_id: str = Field(alias="application_id")


class MasMetricTriggerMessage(BaseTriggerMessage):
    metric_name: Optional[str] = Field(default=None, alias="metric_name")
    mas_name: Optional[str] = Field(default=None, alias="mas_name")


class ImpactAssessmentTrainingMessage(MasMetricTriggerMessage):
    end_to_end_mode: bool = Field(default=False, alias="end_to_end_mode")
    is_training_step: bool = Field(default=False, alias="is_training_step")


class MultiSessionQueueMessage(BaseQueueMessage):
    session_ids: List[str] = Field(alias="session_ids")
    group_id: str = Field(alias="group_id")


class SimpleQueueMessage(BaseQueueMessage):
    new_attr: str = Field(alias="new_attr")


class SimpleQueueMessageB(BaseQueueMessage):
    random_field: str = Field(alias="random_field")


class SessionDetailMessage(BaseQueueMessage):
    metrics: Dict[str, Any] | None = Field(alias="metrics", default=None)
    input_content: str | None = Field(alias="input_content", default=None)
    input_embedding: List[float] | None = Field(alias="input_embedding", default=None)
    output_content: str | None = Field(alias="output_content", default=None)
    output_embedding: List[float] | None = Field(alias="output_embedding", default=None)
    execution_graph: Dict[str, List] | None = Field(alias="execution_graph", default=None)


class SessionDetail(BaseModel):
    session_id: str = Field(alias="session_id")
    metrics: Dict[str, Any] = Field(alias="metrics")
    input_content: str = Field(alias="input_content")
    input_embedding: List[float] = Field(alias="input_embedding")
    output_content: str = Field(alias="output_content")
    output_embedding: List[float] = Field(alias="output_embedding")
    execution_graph: Dict[str, List] = Field(alias="execution_graph")


class SessionGroupMessage(BaseQueueMessage):
    group_id: str = Field(alias="group_id")
    group_hash: str = Field(alias="group_hash")
    sessions: List[Dict[str, Any]] = Field(alias="sessions", default_factory=list)

    @field_validator("sessions", mode="before")
    @classmethod
    def _none_to_empty(cls, value):
        return value if value is not None else []


class FeedbackMessage:
    def __init__(
        self,
        session_id,
        input: str = "",
        event: str = "",
        workflow: str = "",
        workflow_id: str = "",
        queue_name: str = "",
    ):
        self.session_id = session_id
        self.input = input
        self.event = event
        self.workflow = workflow
        self.workflow_id = workflow_id
        self.queue_name = queue_name
        logger.info(
            f"Created FeedbackMessage with session_id: {session_id}, event: {event}, workflow: {workflow}, workflow_id: {workflow_id}, queue_name: {queue_name}"
        )

    @classmethod
    def from_body(cls, message_body: str, prefix: str = ""):
        payload = json.loads(message_body)
        return cls(
            session_id=payload.get("session_id"),
            input=payload.get("input"),
            event=payload.get("event"),
            workflow=payload.get("workflow"),
            workflow_id=payload.get("workflow_id"),
            queue_name=payload.get("queue_name"),
        )

    async def write_message(self, channel, feedback_queue):
        body = {"session_id": self.session_id}
        if self.input:
            body["input"] = self.input
        if self.event:
            body["event"] = self.event
        if self.workflow:
            body["workflow"] = self.workflow
        if self.workflow_id:
            body["workflow_id"] = self.workflow_id
        if self.queue_name:
            body["queue_name"] = self.queue_name
        logger.info(f"Publishing FeedbackMessage to {feedback_queue}")
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=feedback_queue,
        )

    def get_session_id(self):
        return self.session_id

    def dump_message(self):
        return json.dumps(
            {
                "session_id": self.session_id,
                "input": self.input,
                "event": self.event,
                "workflow": self.workflow,
                "workflow_id": self.workflow_id,
                "queue_name": self.queue_name,
            }
        )

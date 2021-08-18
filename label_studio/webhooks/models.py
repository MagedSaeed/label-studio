import requests
from core.validators import JSONSchemaValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import logging

from projects.models import Project
from tasks.models import Task, Annotation
from .serializers_for_hooks import (
    OnlyIDWebhookSerializer,
    ProjectWebhookSerializer,
    TaskWebhookSerializer,
    AnnotationWebhookSerializer,
)

HEADERS_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^[a-zA-Z0-9-_]+$": {"type": "string"},
    },
    "maxProperties": 10,
    "additionalProperties": False,
}


class Webhook(models.Model):
    """Model of webhooks.

    If webhook has not null project field -- it's project webhook
    """

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='webhooks')

    project = models.ForeignKey(
        'projects.Project', null=True, on_delete=models.CASCADE, related_name='webhooks', default=None
    )

    url = models.URLField(_('URL of webhook'), max_length=2048, help_text=_('URL of webhook'))

    send_payload = models.BooleanField(
        _("does webhook send the payload"), default=True, help_text=('If value is False send only action')
    )

    send_for_all_actions = models.BooleanField(
        _("Use webhook for all actions"),
        default=True,
        help_text=('If value is False - used only for actions from WebhookAction'),
    )

    headers = models.JSONField(
        _("request extra headers of webhook"),
        validators=[JSONSchemaValidator(HEADERS_SCHEMA)],
        default=dict,
        help_text=('Key Value Json of headers'),
    )

    is_active = models.BooleanField(
        _("is webhook active"),
        default=True,
        help_text=('If value is False the webhook is disabled'),
    )

    created_at = models.DateTimeField(_('created at'), auto_now_add=True, help_text=_('Creation time'))
    updated_at = models.DateTimeField(_('updated at'), auto_now=True, help_text=_('Last update time'))

    def get_actions(self):
        return WebhookAction.objects.filter(webhook=self).values_list('action', flat=True)

    def validate_actions(self, actions):
        actions_meta = [WebhookAction.ACTIONS[action] for action in actions]
        if self.project and any((meta.get('organization-only') for meta in actions_meta)):
            raise ValidationError("Project webhook can't contain organization-only action.")
        return actions

    def set_actions(self, actions):
        if not actions:
            actions = set()
        actions = set(actions)
        old_actions = set(self.get_actions())

        for new_action in list(actions - old_actions):
            WebhookAction.objects.create(webhook=self, action=new_action)

        WebhookAction.objects.filter(webhook=self, action__in=(old_actions - actions)).delete()

    def has_permission(self, user):
        return self.organization.has_user(user)

    class Meta:
        db_table = 'webhook'


class WebhookAction(models.Model):
    PROJECT_CREATED = 'PROJECT_CREATED'
    PROJECT_UPDATED = 'PROJECT_UPDATED'
    PROJECT_DELETED = 'PROJECT_DELETED'

    TASKS_CREATED = 'TASKS_CREATED'
    TASKS_DELETED = 'TASKS_DELETED'

    ANNOTATION_CREATED = 'ANNOTATION_CREATED'
    ANNOTATION_UPDATED = 'ANNOTATION_UPDATED'
    ANNOTATIONS_DELETED = 'ANNOTATIONS_DELETED'

    ACTIONS = {
        PROJECT_CREATED: {
            'name': _('Project created'),
            'description': _(''),
            'key': 'project',
            'many': False,
            'model': Project,
            'serializer': ProjectWebhookSerializer,
            'organization-only': True,
        },
        PROJECT_UPDATED: {
            'name': _('Project updated'),
            'description': _(''),
            'key': 'project',
            'many': False,
            'model': Project,
            'serializer': ProjectWebhookSerializer,
            'project-field': '__self__',
        },
        PROJECT_DELETED: {
            'name': _('Project deleted'),
            'description': _(''),
            'key': 'project',
            'many': False,
            'model': Project,
            'serializer': OnlyIDWebhookSerializer,
            'organization-only': True,
        },
        TASKS_CREATED: {
            'name': _('Task created'),
            'description': _(''),
            'key': 'tasks',
            'many': True,
            'model': Task,
            'serializer': TaskWebhookSerializer,
            'project-field': 'project',
        },
        TASKS_DELETED: {
            'name': _('Task deleted'),
            'description': _(''),
            'key': 'tasks',
            'many': True,
            'model': Task,
            'serializer': OnlyIDWebhookSerializer,
            'project-field': 'project',
        },
        ANNOTATION_CREATED: {
            'name': _('Annotation created'),
            'description': _(''),
            'key': 'annotation',
            'many': False,
            'model': Annotation,
            'serializer': AnnotationWebhookSerializer,
            'project-field': 'task__project',
        },
        ANNOTATION_UPDATED: {
            'name': _('Annotation updated'),
            'description': _(''),
            'key': 'annotation',
            'many': False,
            'model': Annotation,
            'serializer': AnnotationWebhookSerializer,
            'project-field': 'task__project',
        },
        ANNOTATIONS_DELETED: {
            'name': _('Annotation deleted'),
            'description': _(''),
            'key': 'annotations',
            'many': True,
            'model': Annotation,
            'serializer': OnlyIDWebhookSerializer,
            'project-field': 'task__project',
        },
    }

    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name='actions')

    action = models.CharField(
        _('action of webhook'),
        choices=[[key, value['name']] for key, value in ACTIONS.items()],
        max_length=128,
        db_index=True,
        help_text=_('Action value')
    )

    class Meta:
        db_table = 'webhook_action'
        unique_together = [['webhook', 'action']]
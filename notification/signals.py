from __future__ import absolute_import, unicode_literals
import django.dispatch

should_deliver = django.dispatch.Signal(providing_args=[
    "result", "recipient", "label", "notice_type",
    "extra_context", "sender_user",
])
delivered = django.dispatch.Signal(providing_args=[
    "recipient", "notice_type", "extra_context", "sender_user",
    "medium_id", "backend_label", "backend",
])

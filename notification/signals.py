import django.dispatch

should_deliver = django.dispatch.Signal(providing_args=["result", "user", "label", "extra_context", "on_site", "sender", ])

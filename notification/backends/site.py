from __future__ import absolute_import, unicode_literals
from django.conf import settings
from django.contrib.sites.models import Site
from django.core import urlresolvers
from django.core.exceptions import ImproperlyConfigured
from django.db.models.loading import get_app
from django.template import Context
from django.template.loader import render_to_string
from django.utils.translation import ugettext

from notification import backends
from notification.message import message_to_text

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)
except NameError:
    string_types = (str,)
    integer_types = (int,)

DEFAULT_HTTP_PROTOCOL = getattr(settings, "DEFAULT_HTTP_PROTOCOL", "http")


class SiteBackend(backends.BaseBackend):
    """
    The site backend.
    """
    spam_sensitivity = 1
        
    def deliver(self, recipient, sender, notice_type, extra_context):
        # TODO: require this to be passed in extra_context
        current_site = Site.objects.get_current()
        notices_url = "{0}://{1}{2}".format(
            DEFAULT_HTTP_PROTOCOL,
            str(Site.objects.get_current()),
            urlresolvers.reverse("notification_notices"),
        )
        
        # update context with user specific translations
        context = Context({
            "user": recipient,  # Old compatible
            "recipient": recipient,
            "sender": sender,
            "notice": ugettext(notice_type.display),
            "notices_url": notices_url,
            "current_site": current_site,
        })
        context.update(extra_context)
        
        messages = self.get_formatted_messages((
            "notice.html",
        ), notice_type.label, context)
        from notification.models import Notice
        notice = Notice.objects.create(
            recipient=recipient,
            sender=sender,
            notice_type=notice_type,
            message=messages['notice.html'],
            on_site=True,
        )

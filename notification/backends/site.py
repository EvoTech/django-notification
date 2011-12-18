from django.conf import settings
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.db.models.loading import get_app
from django.template import Context
from django.template.loader import render_to_string
from django.utils.translation import ugettext
from django.core.exceptions import ImproperlyConfigured

from notification import backends
from notification.message import message_to_text
from notification.models import Notice


class SiteBackend(backends.BaseBackend):
    spam_sensitivity = 1
        
    def deliver(self, recipient, sender, notice_type, extra_context):
        # TODO: require this to be passed in extra_context
        current_site = Site.objects.get_current()
        notices_url = u"http://%s%s" % (
            unicode(Site.objects.get_current()),
            reverse("notification_notices"),
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

        notice = Notice.objects.create(
            user=user,
            message=messages['notice.html'],
            notice_type=notice_type,
            on_site=True,
        )

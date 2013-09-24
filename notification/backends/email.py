from __future__ import absolute_import, unicode_literals
from django.conf import settings
from django.contrib.sites.models import Site
from django.core import urlresolvers
from django.core import signing
from django.db.models.loading import get_app
from django.template import Context
from django.template.loader import render_to_string
from django.utils.translation import ugettext
from django.core.exceptions import ImproperlyConfigured

if 'mailer' in settings.INSTALLED_APPS:
    from mailer import send_mail, send_html_mail
else:
    from django.core.mail import send_mail, EmailMultiAlternatives

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


class EmailBackend(backends.BaseBackend):
    spam_sensitivity = 2

    def can_send(self, user, notice_type):
        can_send = super(EmailBackend, self).can_send(user, notice_type)
        if can_send and user.email and '@' in user.email and not user.email.startswith('__'):
            return True
        return False

    def deliver(self, recipient, sender, notice_type, extra_context):
        # TODO: require this to be passed in extra_context
        current_site = Site.objects.get_current()
        root_url = "{0}://{1}".format(
            DEFAULT_HTTP_PROTOCOL,
            str(Site.objects.get_current())
        )
        notices_url = "{0}{1}".format(
            root_url,
            urlresolvers.reverse("notification_notices"),
        )
        settings_url = "{0}{1}".format(
            root_url,
            urlresolvers.reverse("notification_notice_settings"),
        )
        unsubscribe_url = "{0}{1}".format(
            root_url,
            urlresolvers.reverse(
                'notificaton_unsubscribe',
                args=[signing.dumps([recipient.pk, self.medium_id, notice_type.label]), ]
            )
        )
        unsubscribe_all_url = "{0}{1}".format(
            root_url,
            urlresolvers.reverse(
                'notificaton_unsubscribe',
                args=[signing.dumps([recipient.pk, self.medium_id, None]), ]
            )
        )

        # update context with user specific translations
        context = Context({
            "user": recipient,  # Old compatible
            "recipient": recipient,
            "sender": sender,
            "notice": ugettext(notice_type.display),
            "notice_type": notice_type,
            "notices_url": notices_url,
            "settings_url": settings_url,
            "unsubscribe_url": unsubscribe_url,
            "unsubscribe_all_url": unsubscribe_all_url,
            "current_site": current_site,
        })
        context.update(extra_context)

        messages = self.get_formatted_messages((
            "short.txt",
            "full.txt",
            "full.html",
        ), notice_type.label, context)

        # Checking, is it default full.html?
        # Fix me. Is it exists a better way to detect is_html?
        # Add marker "<!-- default template //-->"?
        if messages['full.html'].strip() != ugettext(notice_type.display).strip():
            is_html = True
        else:
            is_html = False

        subject = "".join(render_to_string("notification/email_subject.txt", {
            "message": messages["short.txt"],
        }, context).splitlines())

        body = render_to_string("notification/email_body.txt", {
            "message": messages["full.txt"],
        }, context)

        body_html = render_to_string("notification/email_body.html", {
            "message": messages["full.html"],
        }, context)

        if not is_html:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                      [recipient.email])
        else:
            if 'send_html_mail' in globals():
                send_html_mail(subject, body, messages['full.html'],
                               settings.DEFAULT_FROM_EMAIL, [recipient.email])
            else:
                msg = EmailMultiAlternatives(subject, body,
                                             settings.DEFAULT_FROM_EMAIL,
                                             [recipient.email])
                msg.attach_alternative(body_html, "text/html")
                msg.send()

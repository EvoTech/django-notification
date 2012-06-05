from django.conf import settings
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
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
            "short.txt",
            "full.txt",
            "full.html",
        ), notice_type.label, context)

        # Fix me. Is it exists a better way to detect is_html?
        # Chicking, is it default full.html?
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

        body_html = messages['full.html']
        
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

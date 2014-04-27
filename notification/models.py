from __future__ import absolute_import, unicode_literals
import sys

try:
    import cPickle as pickle
except ImportError:
    import pickle

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.query import QuerySet, RawQuerySet
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.utils import translation
from django.utils import timezone

from django.contrib.auth.models import User

from notification import backends
from notification.message import encode_message
from notification.managers import NoticeManager, ObservedItemManager, QueryDataManager
from notification.signals import should_deliver, delivered, configure
from notification.utils import permission_by_label

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)
except NameError:
    string_types = (str,)
    integer_types = (int,)

QUEUE_ALL = getattr(settings, "NOTIFICATION_QUEUE_ALL", False)


class LanguageStoreNotAvailable(Exception):
    pass


class NoticeType(models.Model):

    label = models.CharField(_("label"), max_length=40, unique=True)
    display = models.CharField(_("display"), max_length=50)
    description = models.CharField(_("description"), max_length=100)

    # by default only on for media with sensitivity less than or equal to this number
    default = models.IntegerField(_("default"))

    def __str__(self):
        return self.label

    class Meta:
        ordering = ("label", )
        verbose_name = _("notice type")
        verbose_name_plural = _("notice types")


NOTIFICATION_BACKENDS = backends.load_backends()

NOTICE_MEDIA = []
NOTICE_MEDIA_DEFAULTS = {}
for key, backend in list(NOTIFICATION_BACKENDS.items()):
    # key is a tuple (medium_id, backend_label)
    NOTICE_MEDIA.append(key)
    NOTICE_MEDIA_DEFAULTS[key[0]] = backend.spam_sensitivity


class NoticeSetting(models.Model):
    """
    Indicates, for a given user, whether to send notifications
    of a given type to a given medium.
    """

    user = models.ForeignKey(User, verbose_name=_("user"))
    notice_type = models.ForeignKey(NoticeType, verbose_name=_("notice type"))
    medium = models.CharField(_("medium"), max_length=1, choices=NOTICE_MEDIA)
    send = models.BooleanField(_("send"))

    class Meta:
        verbose_name = _("notice setting")
        verbose_name_plural = _("notice settings")
        unique_together = ("user", "notice_type", "medium")


def get_notification_setting(user, notice_type, medium):
    try:
        return NoticeSetting.objects.get(user=user, notice_type=notice_type, medium=medium)
    except NoticeSetting.DoesNotExist:
        default = (NOTICE_MEDIA_DEFAULTS[medium] <= notice_type.default)
        setting = NoticeSetting(user=user, notice_type=notice_type, medium=medium, send=default)
        setting.save()
        return setting


def should_send(user, notice_type, medium):
    return get_notification_setting(user, notice_type, medium).send


class NoticeUid(models.Model):
    """Prevents duplicates for same object by differents observed items"""
    recipient = models.ForeignKey(User, related_name="recieved_noticesuid", verbose_name=_("recipient"))
    notice_uid = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return "{0} - {1}".format(self.recipient, self.notice_uid)

    class Meta:
        verbose_name = _("notice uid")
        verbose_name_plural = _("notice uids")
        unique_together = [('recipient', 'notice_uid', )]


class Notice(models.Model):

    recipient = models.ForeignKey(User, related_name="recieved_notices", verbose_name=_("recipient"))
    sender = models.ForeignKey(User, null=True, related_name="sent_notices", verbose_name=_("sender"))
    message = models.TextField(_("message"))
    notice_type = models.ForeignKey(NoticeType, verbose_name=_("notice type"))
    added = models.DateTimeField(_("added"), auto_now_add=True, db_index=True)
    unseen = models.BooleanField(_("unseen"), default=True, db_index=True)
    archived = models.BooleanField(_("archived"), default=False, db_index=True)
    on_site = models.BooleanField(_("on site"), db_index=True)

    objects = NoticeManager()

    def __str__(self):
        return self.message

    def archive(self):
        self.archived = True
        self.save()

    def is_unseen(self):
        """
        returns value of self.unseen but also changes it to false.

        Use this in a template to mark an unseen notice differently the first
        time it is shown.
        """
        unseen = self.unseen
        if unseen:
            self.unseen = False
            self.save()
        return unseen

    class Meta:
        ordering = ["-added"]
        verbose_name = _("notice")
        verbose_name_plural = _("notices")

    def get_absolute_url(self):
        return reverse("notification_notice", args=[str(self.pk)])


class NoticeQueueBatch(models.Model):
    """
    A queued notice.
    Denormalized data for a notice.
    """
    pickled_data = models.TextField()


def create_notice_type(label, display, description, default=2, verbosity=1):
    """
    Creates a new NoticeType.

    This is intended to be used by other apps as a post_syncdb manangement step.
    """
    try:
        notice_type = NoticeType.objects.get(label=label)
        updated = False
        if display != notice_type.display:
            notice_type.display = display
            updated = True
        if description != notice_type.description:
            notice_type.description = description
            updated = True
        if default != notice_type.default:
            notice_type.default = default
            updated = True
        if updated:
            notice_type.save()
            if verbosity > 1:
                print("Updated {0} NoticeType".format(label))
    except NoticeType.DoesNotExist:
        NoticeType(label=label, display=display, description=description, default=default).save()
        if verbosity > 1:
            print("Created {0} NoticeType".format(label))


def get_notification_language(user):
    """
    Returns site-specific notification language for this user. Raises
    LanguageStoreNotAvailable if this site does not use translated
    notifications.
    """
    if getattr(settings, "NOTIFICATION_LANGUAGE_MODULE", False):
        try:
            app_label, model_name = settings.NOTIFICATION_LANGUAGE_MODULE.split(".")
            model = models.get_model(app_label, model_name)
            language_model = model._default_manager.get(user__id__exact=user.id)
            if hasattr(language_model, "language"):
                return language_model.language
        except (ImportError, ImproperlyConfigured, model.DoesNotExist):
            raise LanguageStoreNotAvailable
    raise LanguageStoreNotAvailable


def get_formatted_messages(formats, label, context):
    """
    Returns a dictionary with the format identifier as the key. The values are
    are fully rendered templates with the given context.
    """
    format_templates = {}
    for format in formats:
        # conditionally turn off autoescaping for .txt extensions in format
        if format.endswith(".txt"):
            context.autoescape = False
        else:
            context.autoescape = True
        format_templates[format] = render_to_string((
            "notification/{0}/{1}".format(label, format),
            "notification/{0}".format(format)), context_instance=context)
    return format_templates


def send_now(users, label, extra_context=None, on_site=True, sender=None):
    """
    Creates a new notice.

    This is intended to be how other apps create new notices.

    notification.send(user, "friends_invite_sent", {
        "spam": "eggs",
        "foo": "bar",
    )

    You can pass in on_site=False to prevent the notice emitted from being
    displayed on the site.
    """
    sent = {}
    if extra_context is None:
        extra_context = {}

    notice_type = NoticeType.objects.get(label=label)
    notice_uid = extra_context.get('notice_uid', None)

    current_language = translation.get_language()
    current_timezone = timezone.get_current_timezone()

    for user in users:
        obj = extra_context.get('context_object',
                                extra_context.get('observed', None))
        if obj and not user.has_perm(permission_by_label(obj, 'view'), obj):
            continue

        if notice_uid:
            try:
                NoticeUid.objects.get(notice_uid=notice_uid, recipient=user)
                continue
            except NoticeUid.DoesNotExist:
                NoticeUid.objects.create(notice_uid=notice_uid, recipient=user)

        # Deprecated
        # get user language for user from language store defined in
        # NOTIFICATION_LANGUAGE_MODULE setting
        try:
            language = get_notification_language(user)
        except LanguageStoreNotAvailable:
            language = None

        # Deprecated
        result = {'pass': True}
        results = should_deliver.send(
            sender=Notice,
            result=result,
            recipient=user,
            label=label,
            notice_type=notice_type,
            extra_context=extra_context,
            sender_user=sender
        )
        if not result['pass']:
            continue
        if False in [i[1] for i in results]:
            continue

        results = configure.send(
            sender=Notice,
            recipient=user,
            label=label,
            notice_type=notice_type,
            extra_context=extra_context,
            sender_user=sender
        )
        configs = [i[1] for i in results if i[1]]
        configs.sort(key=lambda x: x.get('order', 0))
        # TODO: Let pass config as argument of function, or as item of extra_context???
        config = {
            'language': language or current_language,
            'timezone': current_timezone,
            'send': True,
        }
        for i in configs:
            config.update(i)

        if not config['send']:
            continue

        with translation.override(config['language']), timezone.override(config['timezone']):
            for (medium_id, backend_label), backend in list(NOTIFICATION_BACKENDS.items()):
                if backend.can_send(user, notice_type):
                    backend.deliver(user, sender, notice_type, extra_context)
                    delivered.send(
                        sender=Notice,
                        recipient=user,
                        notice_type=notice_type,
                        extra_context=extra_context,
                        sender_user=sender,
                        medium_id=medium_id,
                        backend_label=backend_label,
                        backend=backend
                    )
                    sent.setdefault(backend_label, 0)
                    sent[backend_label] += 1

    return sent


def send(*args, **kwargs):
    """
    A basic interface around both queue and send_now. This honors a global
    flag NOTIFICATION_QUEUE_ALL that helps determine whether all calls should
    be queued or not. A per call ``queue`` or ``now`` keyword argument can be
    used to always override the default global behavior.
    """
    queue_flag = kwargs.pop("queue", False)
    now_flag = kwargs.pop("now", False)
    assert not (queue_flag and now_flag), "'queue' and 'now' cannot both be True."
    if queue_flag:
        return queue(*args, **kwargs)
    elif now_flag:
        return send_now(*args, **kwargs)
    else:
        if QUEUE_ALL:
            return queue(*args, **kwargs)
        else:
            return send_now(*args, **kwargs)


def queue(users, label, extra_context=None, on_site=True, sender=None):
    """
    Queue the notification in NoticeQueueBatch. This allows for large amounts
    of user notifications to be deferred to a seperate process running outside
    the webserver.
    """
    if extra_context is None:
        extra_context = {}
    if isinstance(users, (QuerySet, RawQuerySet)):
        users = list(users.values_list("pk", flat=True))
        # users = users.query  # ???
    else:
        users = [u.pk if isinstance(u, models.Model) else u for u in users]
    notices = [(users, label, extra_context, on_site, sender, ), ]
    NoticeQueueBatch(pickled_data=pickle.dumps(notices).encode("base64")).save()


class ObservedItem(models.Model):

    user = models.ForeignKey(User, verbose_name=_("user"))

    content_type = models.ForeignKey(ContentType)
    object_id = models.CharField(max_length=255, db_index=True)
    observed_object = generic.GenericForeignKey("content_type", "object_id")

    notice_type = models.ForeignKey(NoticeType, verbose_name=_("notice type"))

    added = models.DateTimeField(_("added"), auto_now_add=True, db_index=True)

    # the signal that will be listened to send the notice
    signal = models.CharField(
        verbose_name=_("signal"),
        max_length=255,
        db_index=True
    )

    objects = ObservedItemManager()

    class Meta:
        ordering = ["-added"]
        verbose_name = _("observed item")
        verbose_name_plural = _("observed items")

    def send_notice(self, extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context.update({"observed": self.observed_object})
        send([self.user], self.notice_type.label, extra_context)


def observe(observed, observer, notice_type_label, signal="post_save"):
    """
    Create a new ObservedItem.

    To be used by applications to register a user as an observer for some object.
    """
    perm = permission_by_label(observed, 'view')
    if not (observer.is_authenticated() and observer.has_perm(perm, observed)):
        raise PermissionDenied()
    notice_type = NoticeType.objects.get(label=notice_type_label)
    observed_item = ObservedItem(
        user=observer, observed_object=observed,
        notice_type=notice_type, signal=signal
    )
    observed_item.save()
    return observed_item


def stop_observing(observed, observer, signal="post_save"):
    """
    Remove an observed item.
    """
    observed_item = ObservedItem.objects.get_for(observed, observer, signal)
    observed_item.delete()


def send_observation_notices_for(observed, signal="post_save",
                                 extra_context=None, on_site=True,
                                 sender=None):
    """
    Send a notice for each registered user about an observed object.
    """
    if extra_context is None:
        extra_context = {}
    observed_items = ObservedItem.objects.all_for(observed, signal)
    if QUEUE_ALL:
        rows = observed_items.values("user", "notice_type__label")
        extra_context.update({'observed': observed, })
        notices = []
        label_users = {}
        for row in rows:
            users = label_users.setdefault(row["notice_type__label"], [])
            users.append(row["user"])
        for label, users in label_users.items():
            notices.append((users, label, extra_context, on_site, sender))
        if notices:
            NoticeQueueBatch(
                pickled_data=pickle.dumps(notices).encode("base64")
            ).save()

    else:
        for observed_item in observed_items:
            observed_item.send_notice(extra_context)
    return observed_items


def is_observing(observed, observer, signal="post_save"):
    if not observer.is_authenticated():
        return False
    try:
        observed_items = ObservedItem.objects.get_for(observed, observer, signal)
        return True
    except ObservedItem.DoesNotExist:
        return False
    except ObservedItem.MultipleObjectsReturned:
        return True


# Use carring to pass parameters (context_object, etc.)
def handle_observations(sender, instance, *args, **kw):
    send_observation_notices_for(instance)


class QueryData(models.Model):
    """Query Data

    Allows to observe objects from search list with given query data.
    """
    handler = models.CharField(max_length=100, db_index=True)
    hash = models.BigIntegerField(db_index=True)
    pickled_data = models.TextField()

    objects = QueryDataManager()

    class Meta:
        unique_together = (('handler', 'hash'),)

    def __str__(self):
        return getattr(
            self.handler_instance,
            'get_verbose_name',
            lambda: "{0}: {1}".format(type(self).__name__, str(self.data))
        )()

    def get_absolute_url(self):
        return getattr(
            self.handler_instance,
            'get_absolute_url',
            lambda: "#"
        )()

    @property
    def data(self):
        """Gets data"""
        return pickle.loads(str(self.pickled_data).decode("base64"))

    @data.setter
    def data(self, data):
        """Sets data"""
        self.pickled_data = pickle.dumps(data).encode("base64")
        self.hash = QueryData.objects.make_hash(data)

    @property
    def handler_instance(self):
        """Returns handler instance."""
        mod_name, obj_name = self.handler.rsplit('.', 1)
        __import__(mod_name)
        mod = sys.modules[mod_name]
        handler = getattr(mod, obj_name)
        # In simplest case, handler can be a dict.
        obj = handler(self.data)
        obj.is_valid()
        return obj

# Python 2.* compatible
try:
    unicode
except NameError:
    pass
else:
    for cls in (NoticeType, NoticeUid, Notice, QueryData):
        cls.__unicode__ = cls.__str__
        cls.__str__ = lambda self: self.__unicode__().encode('utf-8')

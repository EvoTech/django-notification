from __future__ import absolute_import, unicode_literals
import copy
from django.db import models
from django.contrib.contenttypes.models import ContentType

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)
except NameError:
    string_types = (str,)
    integer_types = (int,)


class NoticeManager(models.Manager):

    def notices_for(self, user, archived=False, unseen=None, on_site=None, sent=False):
        """
        returns Notice objects for the given user.

        If archived=False, it only include notices not archived.
        If archived=True, it returns all notices for that user.

        If unseen=None, it includes all notices.
        If unseen=True, return only unseen notices.
        If unseen=False, return only seen notices.
        """
        if sent:
            lookup_kwargs = {"sender": user}
        else:
            lookup_kwargs = {"recipient": user}
        qs = self.filter(**lookup_kwargs)
        if not archived:
            self.filter(archived=archived)
        if unseen is not None:
            qs = qs.filter(unseen=unseen)
        if on_site is not None:
            qs = qs.filter(on_site=on_site)
        return qs

    def unseen_count_for(self, recipient, **kwargs):
        """
        returns the number of unseen notices for the given user but does not
        mark them seen
        """
        return self.notices_for(recipient, unseen=True, **kwargs).count()

    def received(self, recipient, **kwargs):
        """
        returns notices the given recipient has recieved.
        """
        kwargs["sent"] = False
        return self.notices_for(recipient, **kwargs)

    def sent(self, sender, **kwargs):
        """
        returns notices the given sender has sent
        """
        kwargs["sent"] = True
        return self.notices_for(sender, **kwargs)


class ObservedItemManager(models.Manager):

    def all_for(self, observed, signal):
        """
        Returns all ObservedItems for an observed object,
        to be sent when a signal is emited.
        """
        content_type = ContentType.objects.get_for_model(observed)
        observed_items = self.filter(content_type=content_type, object_id=observed.id, signal=signal)
        return observed_items

    def get_for(self, observed, observer, signal):
        content_type = ContentType.objects.get_for_model(observed)
        observed_item = self.get(content_type=content_type, object_id=observed.id, user=observer, signal=signal)
        return observed_item


class QueryDataManager(models.Manager):
    """QueryData Manager"""

    ignored_values = (None, "", [], (), {}, set(), frozenset())

    def get_for(self, handler, data):
        """Returns QueryData instance for given handler and data"""
        if not isinstance(handler, string_types):
            if not isinstance(handler, type):
                handler = type(handler)
            handler = "{0}.{1}".format(handler.__module__, handler.__name__)
        data = self.prepare_data(data)
        try:
            return self.get(
                handler=handler,
                hash=self.make_hash(data)
            )
        except self.model.DoesNotExist:
            obj = self.model()
            obj.handler = handler
            obj.data = data
            obj.save()
            return obj

    def make_hash(self, obj):
        """
        Makes a hash from a dictionary, list, tuple or set to any level, that
        contains only other hashable types (including any lists, tuples, sets,
        and dictionaries).
        """
        if isinstance(obj, (tuple, list)):
            return tuple(sorted([self.make_hash(e) for e in obj]))

        elif isinstance(obj, set):
            return frozenset([self.make_hash(e) for e in obj])

        elif isinstance(obj, dict):
            new_obj = {}
            for k, v in obj.items():
                new_obj[k] = self.make_hash(v)
            return hash(frozenset(new_obj.items()))

        return hash(obj)

    def prepare_data(self, obj):
        """Prepares data."""
        # Do we need keep empty values, because they can override
        # the default value of form???
        # On the other hand, during lifetime of object,
        # the number of parameters can be changed.
        # I think, that better to remove the empty values
        # to be independent of code changes.
        ignored_values = self.ignored_values
        if isinstance(obj, (tuple, list)):
            new_obj = []
            for v in obj:
                new_v = self.prepare_data(v)
                if new_v in ignored_values:
                    continue
                new_obj.append(new_v)
            return tuple(new_obj)

        elif isinstance(obj, (set, frozenset)):
            new_obj = []
            for v in obj:
                new_v = self.prepare_data(v)
                if new_v in ignored_values:
                    continue
                new_obj.append(new_v)
            return frozenset(new_obj)

        elif isinstance(obj, dict):
            new_obj = {}
            for k, v in obj.items():
                new_v = self.prepare_data(v)
                if new_v in ignored_values:
                    continue
                new_obj[k] = self.prepare_data(v)
            return new_obj

        elif isinstance(obj, models.Model):
            # Replace model instance to primary key.
            # Model can be changed during lifetime of pickled_data,
            # that will cause an error.
            return obj.pk

        # Force to str()?
        return obj

import copy

from django import template
from django.utils.translation import ugettext_lazy as _
from django.template.loader import render_to_string
from django.contrib.contenttypes.models import ContentType

from classytags.core import Tag, Options
from classytags.arguments import Argument, KeywordArgument, MultiKeywordArgument

from notification.models import is_observing, ObservedItem
from notification.utils import permission_by_label

register = template.Library()


class ObserveLinkTag(Tag):
    name = 'observe_link'
    options = Options(
        Argument('obj', required=True),
        Argument('signal', required=True),
        Argument('notice_type', required=True),
        MultiKeywordArgument(
            'kwa',
            required=False,
            default={'text_observe': _("Observe"),
                     'text_stop_observing': _("Stop observing"), }
        ),
        'as',
        Argument('varname', required=False, resolve=True)
    )

    def render_tag(self, context, obj, signal, notice_type, kwa, varname):
        observer = context['request'].user
        content_type = ContentType.objects.get_for_model(obj)
        observed = False
        if is_observing(observed=obj, observer=observer, signal=signal):
            observed = True

        result = ''
        perm = permission_by_label(obj, notice_type)
        allowed = observer.is_authenticated() and observer.has_perm(perm, obj)

        if allowed:
            local_context = copy.copy(context)
            local_context.update(kwa)
            local_context.update({
                "object": obj,
                "object_id": obj.pk,
                "content_type_id": content_type.pk,
                'observer': observer,
                "signal": signal,
                "notice_type": notice_type,
                "observed": observed,
            })
            result = render_to_string('notification/observe_link.html',
                                      local_context)

        if varname:
            context[varname] = result
            return ''
        return result

register.tag(ObserveLinkTag)

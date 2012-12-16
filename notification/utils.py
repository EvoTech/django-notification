from __future__ import absolute_import, unicode_literals


def permission_by_label(model, label):
    """Get Django permission code for specified label.

    See https://docs.djangoproject.com/en/dev/topics/auth/#default-permissions
    """

    permission_code = '{app}.{perm}_{mod}'.format(
        app=model._meta.app_label,
        perm=label,
        mod=model._meta.module_name
    )
    return permission_code

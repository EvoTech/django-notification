import inspect


def permission_by_label(model, label):
    """Get Django permission code for specified label.

    See https://docs.djangoproject.com/en/dev/topics/auth/#default-permissions
    """

    if not inspect.isclass(model):
        model = model.__class__

    permission_code = '{app}.{perm}_{mod}'.format(
        app=model._meta.app_label,
        perm='observe_{0}'.format(label),
        mod=model._meta.module_name
    )
    return permission_code

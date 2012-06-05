from django.contrib import admin

from notification.models import NoticeType, NoticeSetting, Notice, ObservedItem, NoticeQueueBatch


class NoticeTypeAdmin(admin.ModelAdmin):
    list_display = ["label", "display", "description", "default", ]
    search_fields = ["label", "display", "description", ]


class NoticeSettingAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "notice_type", "medium", "send", ]
    list_editable = ["send", ]
    list_filter = ["notice_type", "medium", "send", ]
    search_fields = ['user__username', 'user__email', ]
    raw_id_fields = ["user", ]


class NoticeAdmin(admin.ModelAdmin):
    list_display = ["message", "recipient", "sender", "notice_type",
                    "added", "unseen", "archived", ]
    search_fields = ['recipient__username', 'recipient__email', ]
    raw_id_fields = ["recipient", "sender", ]


class ObservedItemAdmin(admin.ModelAdmin):
    list_display = ["user", "content_type", "object_id", "observed_object",
                    "notice_type", "signal", "added", ]
    list_filter = ["content_type", "notice_type", "signal", ]
    search_fields = ['user__username', 'user__email', ]
    raw_id_fields = ["user", ]

admin.site.register(NoticeQueueBatch)
admin.site.register(NoticeType, NoticeTypeAdmin)
admin.site.register(NoticeSetting, NoticeSettingAdmin)
admin.site.register(Notice, NoticeAdmin)
admin.site.register(ObservedItem, ObservedItemAdmin)

from django.contrib import admin
from .models import order
from simple_history.admin import SimpleHistoryAdmin



# Register your models here.

admin.site.register(order, SimpleHistoryAdmin)



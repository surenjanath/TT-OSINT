from django.contrib import admin
from .models import Incident


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        'incident_type', 'category', 'location_name', 'region',
        'severity', 'status', 'confidence_score', 'incident_date',
    )
    list_filter = ('category', 'severity', 'status', 'region')
    search_fields = ('incident_type', 'description', 'location_name')
    date_hierarchy = 'incident_date'
    list_editable = ('status',)



"""
WSGI config for tt_osint project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tt_osint.settings')
application = get_wsgi_application()

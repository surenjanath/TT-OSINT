"""
ASGI config for tt_osint project.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tt_osint.settings')
application = get_asgi_application()

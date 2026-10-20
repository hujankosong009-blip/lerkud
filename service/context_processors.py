from .services import site_config

def branding(request):
    return {'branding':site_config()}

from django.utils.cache import add_never_cache_headers

class PreventBackCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Add strict headers to prevent caching for all responses
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "Sat, 01 Jan 2000 00:00:00 GMT"
        return response

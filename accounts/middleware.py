from django.utils.cache import add_never_cache_headers

class PreventBackCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Add headers to prevent caching for all responses
        # Cache-Control: no-cache, no-store, must-revalidate, max-age=0
        add_never_cache_headers(response)
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

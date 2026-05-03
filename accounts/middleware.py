from django.utils.deprecation import MiddlewareMixin

class PreventBackCacheMiddleware(MiddlewareMixin):
    """
    Middleware to prevent the browser from caching pages.
    This ensures that when a user logs out and clicks the back button,
    they don't see the previous authenticated page.
    """
    def process_response(self, request, response):
        # Set headers to prevent caching
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

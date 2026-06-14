"""
URL configuration for elearning_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.template.loader import render_to_string

def robots_txt(request):
    return HttpResponse(
        "User-agent: *\nDisallow: /admin/\nDisallow: /customadmin/\nDisallow: /api/\nAllow: /\n\nSitemap: https://neolearner.onrender.com/sitemap.xml\n",
        content_type="text/plain",
    )

def sitemap_xml(request):
    from accounts.models import Course
    from django.urls import reverse
    urls = []
    for course in Course.objects.filter(status='PUBLISHED', is_approved=True).only('uid', 'updated_at'):
        urls.append({
            'loc': f"https://neolearner.onrender.com/course/{course.uid}/",
            'lastmod': course.updated_at.strftime('%Y-%m-%d') if course.updated_at else '',
        })
    xml = render_to_string('sitemap_template.xml', {'urls': urls})
    return HttpResponse(xml, content_type="application/xml")

urlpatterns = [
    path('robots.txt', robots_txt),
    path('sitemap.xml', sitemap_xml),
    # path('admin/', admin.site.urls),  # Commented out — uncomment when admin access is needed
    path('', include('accounts.urls')),
    path('customadmin/', include('custom_admin.urls')),
]

handler404 = 'custom_admin.views.error_404'
handler500 = 'custom_admin.views.error_500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

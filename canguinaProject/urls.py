"""
URL configuration for canguinaProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from ecanguinha import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('home/', views.home, name='home'),
    path('localizacao/', views.localizacao, name='localizacao'),
    path('sobre/', views.about, name='about'),  # Nova URL
    path('contato/', views.contact, name='contact'),  # Nova URL
    path('api/get_lat_long/', views.get_lat_long, name='get_lat_long'),  # API para obter latitude e longitude
    path('listar_produtos/', views.listar_produtos, name='listar_produtos'),  # Adicione esta linha
    path('avaliar/', views.avaliar, name='avaliar'),
    path('submit/', views.submit_feedback, name='submit_feedback'),
    path('agradecimento/', views.agradecimento, name='agradecimento'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
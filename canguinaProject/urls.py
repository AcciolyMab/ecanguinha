from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from ecanguinha import views
from django.http import JsonResponse


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.localizacao, name='localizacao'),
    path('home/', views.home, name='home'),
    path('localizacao/', views.localizacao, name='localizacao'),
    path('sobre/', views.about, name='about'),
    path('contato/', views.contact, name='contact'),
    path('api/get_lat_long/', views.get_lat_long, name='get_lat_long'),
    path('progresso-status/', views.progresso_status, name='progresso_status'),
    #path('listar_produtos/', views.listar_produtos, name='listar_produtos'),  # Removido async_to_sync
    path('avaliar/', views.avaliar, name='avaliar'),
    path('submit/', views.submit_feedback, name='submit_feedback'),
    path('agradecimento/', views.agradecimento, name='agradecimento'),
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    # URL para iniciar a busca (substitui a antiga 'listar_produtos')
    path('api/iniciar-busca/', views.iniciar_busca_produtos, name='iniciar_busca_produtos'),
    # URL para verificar o status da tarefa
    path('api/task-status/', views.get_task_status, name='get_task_status'),
    # URL para mostrar o resultado final
    path('resultado/<str:task_id>/', views.mostrar_resultado, name='mostrar_resultado'),
    path("processar_combustivel/", views.processar_combustivel, name="processar_combustivel"),
    path('.well-known/appspecific/com.chrome.devtools.json', lambda request: JsonResponse({}, status=204)),
]

# Configuração para arquivos estáticos em modo DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
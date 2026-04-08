from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('editions/', views.EditionListView.as_view(), name='edition-list'),
    path('editions/<int:pk>/', views.EditionDetailView.as_view(), name='edition-detail'),
    path('editions/generate/', views.GenerateEditionView.as_view(), name='generate-edition'),
]

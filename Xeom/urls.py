from django.urls import path
from . import views

urlpatterns = [
    # Order CRUD URLs
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('list/', views.OrderListView.as_view(), name='order_list'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('create/', views.OrderCreateView.as_view(), name='order_create'),
    path('<str:order_number>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('<str:order_number>/update/', views.OrderUpdateView.as_view(), name='order_update'),
    path('<str:order_number>/delete/', views.OrderDeleteView.as_view(), name='order_delete'),
    path('orders/export/xls/', views.export_orders_xls, name='export_orders_xls'),

    
    # API URLs
    path('api/supervisors/', views.get_supervisors, name='get_supervisors'),
    path('api/sales-executives/', views.get_sales_executives, name='get_sales_executives'),
]
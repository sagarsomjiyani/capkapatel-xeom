from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin,PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from .models import order
from .forms import OrderDetailForm, OrderCreateForm
from django.contrib.auth.models import User
from django.views.generic import TemplateView,View
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
import json
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.contrib.auth.forms import AuthenticationForm

@method_decorator([sensitive_post_parameters(),csrf_protect, never_cache], name='dispatch')
class LoginView(View):
    template_name = 'login.html'
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        
        form = AuthenticationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)
        
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            remember_me = request.POST.get('remember_me')
            
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                
                # Handle remember me functionality
                if not remember_me:
                    request.session.set_expiry(0)  # Session expires when browser closes
                else:
                    request.session.set_expiry(1209600)  # Remember for 2 weeks
                
                messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                
                # Redirect to next page or dashboard
                next_page = request.GET.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        
        return render(request, self.template_name, {'form': form})

class LogoutView(View):
    def get(self, request):
        return self.post(request)
    
    def post(self, request):
        if request.user.is_authenticated:
            username = request.user.get_full_name() or request.user.username
            logout(request)
            messages.success(request, f'You have been successfully logged out. Goodbye, {username}!')
        
        return redirect('login')

##################################################################################################################################
##################################################################################################################################

# Class processing the landing page for the admin for updates on the task pending 
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get current date and date ranges
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)
        
        # Basic metrics
        total_orders = order.objects.count()
        completed_orders = order.objects.filter(status='Completed').count()
        in_progress_orders = order.objects.filter(status='In Progress').count()
        
        # Recent orders (last 30 days)
        recent_orders = order.objects.filter(
            order_release__gte=last_30_days
        ).count()
        
        # Orders by status
        status_data = order.objects.values('status').annotate(count=Count('status'))
        
        # Monthly order trends (last 6 months)
        monthly_data = []
        for i in range(6):
            month_start = today.replace(day=1) - timedelta(days=i*30)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            orders_count = order.objects.filter(
                order_release__gte=month_start,
                order_release__lte=month_end
            ).count()
            
            monthly_data.append({
                'month': month_start.strftime('%b %Y'),
                'orders': orders_count
            })
        
        monthly_data.reverse()  # Show oldest to newest
        
        # Orders by phase/stage analysis
        phase_analysis = {
            'bom_ready': order.objects.filter(bom_ready__isnull=False).count(),
            'kick_off_meeting': order.objects.filter(kick_off_meeting__isnull=False).count(),
            'scaffolding_installation': order.objects.filter(scaffolding_installation__isnull=False).count(),
            'installation': order.objects.filter(installation__isnull=False).count(),
            'lift_handover': order.objects.filter(lift_handover__isnull=False).count(),
            'license_received': order.objects.filter(license_received__isnull=False).count(),
        }
        
        # Top performing sites (by number of orders)
        top_sites = order.objects.values('site_name').annotate(
            order_count=Count('order_number')
        ).order_by('-order_count')[:5]
        
        # Recent activity (last 10 orders)
        recent_activity = order.objects.select_related(
            'sales_executive', 'supervisor'
        ).order_by('-order_release')[:10]
        
        # Overdue orders (orders without installation date after 90 days)
        overdue_threshold = today - timedelta(days=90)
        overdue_orders = order.objects.filter(
            order_release__lt=overdue_threshold,
            installation__isnull=True,
            status='In Progress'
        ).count()
        
        # Completion rate
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        # Average time to completion (for completed orders)
        completed_with_dates = order.objects.filter(
            status='Completed',
            order_release__isnull=False,
            receipt_by_maintenance__isnull=False
        )
        
        avg_completion_days = 0
        if completed_with_dates.exists():
            total_days = sum([
                (o.receipt_by_maintenance - o.order_release).days 
                for o in completed_with_dates
            ])
            avg_completion_days = total_days / completed_with_dates.count()
        
        # Supervisor performance
        supervisor_performance = User.objects.filter(
            supervisor__isnull=False
        ).annotate(
            total_orders=Count('supervisor'),
            completed_orders=Count('supervisor', filter=Q(supervisor__status='Completed'))
        ).order_by('-total_orders')[:5]
        
        # Alerts and notifications
        alerts = []
        
        # Check for orders without supervisor assigned
        no_supervisor_count = order.objects.filter(
            supervisor__isnull=True,
            status='In Progress'
        ).count()
        
        if no_supervisor_count > 0:
            alerts.append({
                'type': 'warning',
                'message': f'{no_supervisor_count} orders without assigned supervisor'
            })
        
        # Check for overdue orders
        if overdue_orders > 0:
            alerts.append({
                'type': 'danger',
                'message': f'{overdue_orders} orders are overdue (>90 days without installation)'
            })
        
        # Check for recent completions
        recent_completions = order.objects.filter(
            receipt_by_maintenance__gte=last_7_days
        ).count()
        
        if recent_completions > 0:
            alerts.append({
                'type': 'success',
                'message': f'{recent_completions} orders completed in the last 7 days'
            })
        
        # Prepare chart data for JSON
        context.update({
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'in_progress_orders': in_progress_orders,
            'recent_orders': recent_orders,
            'completion_rate': round(completion_rate, 1),
            'avg_completion_days': round(avg_completion_days, 1),
            'overdue_orders': overdue_orders,
            'status_data': json.dumps(list(status_data)),
            'monthly_data': json.dumps(monthly_data),
            'phase_analysis': phase_analysis,
            'top_sites': top_sites,
            'recent_activity': recent_activity,
            'supervisor_performance': supervisor_performance,
            'alerts': alerts,
        })
        
        return context

##################################################################################################################################
##################################################################################################################################

class OrderListView(LoginRequiredMixin, ListView):
    model = order
    template_name = 'order_list.html'
    context_object_name = 'orders'
    paginate_by = 10
    
    def get_queryset(self):
        if self.request.user.groups.filter(name='Admin').exists():
            queryset = order.objects.all()
        elif self.request.user.groups.filter(name='Supervisor HOD').exists():
            queryset = order.objects.all().filter(supervisor_decided__isnull=True).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Supervisor').exists():
            queryset = order.objects.all().filter(installation__isnull=True).filter(supervisor=self.request.user).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Designer').exists():
            queryset = order.objects.all().filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Store manager').exists():
            queryset = order.objects.all().filter(scaffolding_delivery__isnull=True).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Purchase manager').exists():
            queryset = order.objects.all().filter(installation__isnull=True).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='License consultant').exists():
            queryset = order.objects.all().filter(license_received__isnull=True).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Sales Person').exists():
            queryset = order.objects.all().filter(installation__isnull=True).filter(sales_executive=self.request.user).filter(order_release__isnull=False)
        elif self.request.user.groups.filter(name='Maintenance HOD').exists():
            queryset = order.objects.all().filter(received_by_maintenance_hod=True).filter(order_release__isnull=False).filter(email_to_maintenance=False)
        else:
            queryset = order.objects.all().filter(order_release__isnull=False)
        status = self.request.GET.get('status')
        search = self.request.GET.get('search')
        
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                order_number__icontains=search
            ) | queryset.filter(
                site_name__icontains=search
            ) | queryset.filter(
                equipment_number__icontains=search
            )
        
        return queryset.order_by('-order_release')

class OrderDetailView(LoginRequiredMixin, DetailView):
    model = order
    template_name = 'order_detail.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_number'
    
    def get_object(self):
        return get_object_or_404(order, order_number=self.kwargs['order_number'])

class OrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = order
    form_class = OrderCreateForm
    template_name = 'order_form.html'
    success_url = reverse_lazy('order_list')
    permission_required = 'Xeom.add_order'
    
    def form_valid(self, form):
        messages.success(self.request, 'Order created successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Order'
        context['button_text'] = 'Create Order'
        return context

class OrderUpdateView(LoginRequiredMixin, UpdateView):
    model = order
    form_class = OrderDetailForm
    template_name = 'order_form.html'
    pk_url_kwarg = 'order_number'
    
    def get_object(self):
        return get_object_or_404(order, order_number=self.kwargs['order_number'])
    
    def get_success_url(self):
        return reverse_lazy('order_detail', kwargs={'order_number': self.object.order_number})
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user  # Pass the user to the form
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, 'Order updated successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Update Order'
        context['button_text'] = 'Update Order'
        return context

class OrderDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = order
    template_name = 'order_confirm_delete.html'
    success_url = reverse_lazy('order_list')
    pk_url_kwarg = 'order_number'
    permission_required = 'order.delete_order'
    
    def get_object(self):
        return get_object_or_404(order, order_number=self.kwargs['order_number'])
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Order deleted successfully!')
        return super().delete(request, *args, **kwargs)


# API Views for AJAX
def get_supervisors(request):
    """API endpoint to get supervisors for dynamic loading"""
    supervisors = User.objects.filter(groups__name='Supervisors')
    data = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in supervisors]
    return JsonResponse({'supervisors': data})

def get_sales_executives(request):
    """API endpoint to get sales executives for dynamic loading"""
    executives = User.objects.filter(groups__name='Sales Executives')
    data = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in executives]
    return JsonResponse({'executives': data})



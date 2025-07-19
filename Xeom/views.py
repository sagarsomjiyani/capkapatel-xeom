from django.shortcuts import render, get_object_or_404, redirect, HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin,PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from .models import order
from .forms import OrderDetailForm, OrderCreateForm, UserPasswordChangeForm
from django.contrib.auth.models import User
from django.views.generic import TemplateView,View
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta, date
import json
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.contrib.auth.forms import AuthenticationForm
import openpyxl # Import openpyxl

##################################################################################################################################
##################################################################################################################################

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
class DashboardView1(LoginRequiredMixin, TemplateView):
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
        # elif self.request.user.groups.filter(name='Supervisor HOD').exists():
        #     queryset = order.objects.all().filter(supervisor_decided__isnull=True).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Supervisor').exists():
        #     queryset = order.objects.all().filter(installation__isnull=True).filter(supervisor=self.request.user).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Designer').exists():
        #     queryset = order.objects.all().filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Store manager').exists():
        #     queryset = order.objects.all().filter(scaffolding_delivery__isnull=True).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Purchase manager').exists():
        #     queryset = order.objects.all().filter(installation__isnull=True).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='License consultant').exists():
        #     queryset = order.objects.all().filter(license_received__isnull=True).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Sales Person').exists():
        #     queryset = order.objects.all().filter(installation__isnull=True).filter(sales_executive=self.request.user).filter(order_release__isnull=False)
        # elif self.request.user.groups.filter(name='Maintenance HOD').exists():
        #     queryset = order.objects.all().filter(received_by_maintenance_hod=True).filter(order_release__isnull=False).filter(email_to_maintenance=False)
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

##################################################################################################################################
##################################################################################################################################

class OrderDetailView(LoginRequiredMixin, DetailView):
    model = order
    template_name = 'order_detail.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_number'
    
    def get_object(self):
        return get_object_or_404(order, order_number=self.kwargs['order_number'])

##################################################################################################################################
##################################################################################################################################

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

##################################################################################################################################
##################################################################################################################################

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

##################################################################################################################################
##################################################################################################################################

class OrderDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = order
    template_name = 'order_confirm_delete.html'
    success_url = reverse_lazy('order_list')
    pk_url_kwarg = 'order_number'
    permission_required = 'Xeom.delete_order'
    
    def get_object(self):
        return get_object_or_404(order, order_number=self.kwargs['order_number'])
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Order deleted successfully!')
        return super().delete(request, *args, **kwargs)

##################################################################################################################################
##################################################################################################################################
##################################################################################################################################
##################################################################################################################################

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

##################################################################################################################################
##################################################################################################################################
##################################################################################################################################
##################################################################################################################################

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Initialize basic context
        today = timezone.now().date()
        user_groups = [group.name for group in self.request.user.groups.all()]
        
        context.update({
            'user_groups': user_groups,
            'is_admin': 'Admin' in user_groups,
        })
        
        # Generate worklist for the current user
        context['worklist_orders'] = self._generate_worklist(user_groups, today)
        
        # Add dashboard metrics (primarily for admins)
        context.update(self._get_dashboard_metrics(today))
        
        return context
    
    def _generate_worklist(self, user_groups, today):
        """Generate worklist of pending tasks for the current user"""
        worklist_orders = []
        
        try:
            # Get workflow configuration
            workflow_config = self._get_workflow_config()
            user_allowed_fields = self._get_user_allowed_fields(user_groups, workflow_config)
            
            if not user_allowed_fields:
                return worklist_orders
            
            # Get in-progress orders
            in_progress_orders = order.objects.filter(
                status='In Progress'
            ).select_related('sales_executive', 'supervisor')
            
            # Process each order to find pending tasks
            for order_obj in in_progress_orders:
                pending_task = self._find_pending_task_for_user(
                    order_obj, user_groups, user_allowed_fields, workflow_config, today
                )
                
                if pending_task:
                    worklist_orders.append(pending_task)
            
            # Sort by days pending (most urgent first)
            worklist_orders.sort(key=lambda x: x.get('days_pending', 0), reverse=True)
            
        except Exception as e:
            # Log error but don't break the dashboard
            print(f"Error generating worklist: {e}")
            import traceback
            traceback.print_exc()
        
        return worklist_orders
    
    def _get_workflow_config(self):
        """Get workflow configuration from forms"""
        return {
            'group_mapping': OrderDetailForm.GROUP_ACTIVITY_MAPPING,
            'dependencies': OrderDetailForm.WORKFLOW_DEPENDENCIES,
            'display_names': OrderDetailForm.FIELD_DISPLAY_NAMES,
            # CRITICAL FIX: Include ALL workflow fields, including JSON fields
            'workflow_order': [
                'order_release', 'supervisor', 'bom_ready', 'gad_send_for_sign',
                'kick_off_meeting', 'scaffolding_message', 'scaffolding_delivery',
                'erector', 'erector_file_ready', 'scaffolding_installation',
                'reading_receipt', 'po_release', 'material_dump', 'installation',
                'lift_handover', 'gad_sign_complete', 'form_a_submitted',
                'form_a_permission_received', 'form_b_submitted', 'license_received',
                'license_handover', 'handover_oc_submitted', 'email_to_maintenance',
                'receipt_by_maintenance'
            ]
        }
    
    def _get_user_allowed_fields(self, user_groups, workflow_config):
        """Get fields that the current user is allowed to work on"""
        user_allowed_fields = set()
        
        for group_name in user_groups:
            fields = workflow_config['group_mapping'].get(group_name, [])
            user_allowed_fields.update(fields)
        
        return user_allowed_fields
    
    def _find_pending_task_for_user(self, order_obj, user_groups, user_allowed_fields, workflow_config, today):
        """Find the next pending task for the current user for a specific order"""
        
        # Skip orders without order_release date
        if not order_obj.order_release:
            return None
        
        last_completed_date = order_obj.order_release
        
        # Process workflow in order to find next pending task
        for field_name in workflow_config['workflow_order']:
            field_value = getattr(order_obj, field_name, None)
            
            # Check if this field is completed
            is_completed = self._is_field_completed(field_name, field_value)
            
            if is_completed:
                # Update last completed date
                field_date = self._get_field_date(field_name, field_value)
                if field_date and field_date > last_completed_date:
                    last_completed_date = field_date
                continue
            
            # Field is not completed - check if it's actionable
            if not self._are_prerequisites_met(order_obj, field_name, workflow_config):
                continue
            
            # Check if this field is relevant to the current user
            if field_name not in user_allowed_fields:
                continue
            
            # Apply role-specific business logic
            if not self._is_task_applicable_for_user(order_obj, field_name, user_groups):
                continue
            
            # Found a pending task for this user
            days_pending = (today - last_completed_date).days if last_completed_date else 0
            
            return {
                'order': order_obj,
                'next_action_field': field_name,
                'next_action_display': workflow_config['display_names'].get(field_name, field_name),
                'days_pending': days_pending,
                'last_completed_date': last_completed_date,
                'order_detail_url': reverse('order_detail', kwargs={'order_number': order_obj.order_number})
            }
        
        return None
    
    def _is_field_completed(self, field_name, field_value):
        """Check if a field is completed"""
        if field_name in ['po_release', 'material_dump', 'installation']:
            # JSON fields are completed if they contain data
            return field_value and isinstance(field_value, list) and len(field_value) > 0
        else:
            # Other fields are completed if they have a value
            return field_value is not None
    
    def _get_field_date(self, field_name, field_value):
        """Extract date from field value"""
        if field_name in ['po_release', 'material_dump', 'installation']:
            # For JSON fields, get the latest date
            if not field_value or not isinstance(field_value, list):
                return None
            
            dates = []
            for item in field_value:
                if isinstance(item, dict) and item.get('date'):
                    try:
                        dates.append(datetime.strptime(item['date'], '%Y-%m-%d').date())
                    except (ValueError, TypeError):
                        continue
            
            return max(dates) if dates else None
        else:
            # For date fields, return the date directly
            return field_value if isinstance(field_value, date) else None
    
    def _are_prerequisites_met(self, order_obj, field_name, workflow_config):
        """Check if all prerequisites for a field are met"""
        prerequisites = workflow_config['dependencies'].get(field_name, [])
        
        for prereq_field in prerequisites:
            prereq_value = getattr(order_obj, prereq_field, None)
            
            if not self._is_field_completed(prereq_field, prereq_value):
                return False
        
        return True
    
    def _is_task_applicable_for_user(self, order_obj, field_name, user_groups):
        """Apply role-specific business logic"""
        
        # Supervisor HOD specific logic
        if field_name == 'supervisor' and 'Supervisor HOD' in user_groups:
            return not order_obj.supervisor  # Only if supervisor not assigned
        
        # Regular Supervisor specific logic
        if 'Supervisor' in user_groups:
            supervisor_fields = ['kick_off_meeting', 'scaffolding_message', 'scaffolding_installation', 
                               'installation', 'lift_handover', 'gad_sign_complete']
            if field_name in supervisor_fields:
                return order_obj.supervisor == self.request.user
        
        # Sales Person specific logic
        if 'Sales person' in user_groups:
            sales_fields = ['license_handover', 'handover_oc_submitted']
            if field_name in sales_fields:
                return order_obj.sales_executive == self.request.user
        
        # For other roles, if the field is in their allowed fields, it's applicable
        return True
    
    def _get_dashboard_metrics(self, today):
        """Get dashboard metrics and analytics"""
        try:
            # Basic metrics
            total_orders = order.objects.count()
            completed_orders = order.objects.filter(status='Completed').count()
            in_progress_orders = order.objects.filter(status='In Progress').count()
            
            # Date ranges
            last_30_days = today - timedelta(days=30)
            last_7_days = today - timedelta(days=7)
            
            # Recent orders
            recent_orders = order.objects.filter(order_release__gte=last_30_days).count()
            
            # Completion rate
            completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
            
            # Average completion time
            avg_completion_days = self._calculate_avg_completion_time()
            
            # Status distribution
            status_data = list(order.objects.values('status').annotate(count=Count('status')))
            
            # Monthly trends
            monthly_data = self._get_monthly_trends(today)
            
            # Phase analysis
            phase_analysis = self._get_phase_analysis()
            
            # Top sites
            top_sites = order.objects.values('site_name').annotate(
                order_count=Count('order_number')
            ).order_by('-order_count')[:5]
            
            # Recent activity
            recent_activity = order.objects.select_related(
                'sales_executive', 'supervisor'
            ).order_by('-order_release')[:10]
            
            # Alerts
            alerts = self._generate_alerts(today, last_7_days)
            
            # Supervisor performance
            supervisor_performance = self._get_supervisor_performance()
            
            return {
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'in_progress_orders': in_progress_orders,
                'recent_orders': recent_orders,
                'completion_rate': round(completion_rate, 1),
                'avg_completion_days': round(avg_completion_days, 1),
                'status_data': json.dumps(status_data),
                'monthly_data': json.dumps(monthly_data),
                'phase_analysis': phase_analysis,
                'top_sites': top_sites,
                'recent_activity': recent_activity,
                'supervisor_performance': supervisor_performance,
                'alerts': alerts,
            }
            
        except Exception as e:
            print(f"Error generating dashboard metrics: {e}")
            return {}
    
    def _calculate_avg_completion_time(self):
        """Calculate average completion time for completed orders"""
        try:
            completed_orders = order.objects.filter(
                status='Completed',
                order_release__isnull=False,
                receipt_by_maintenance__isnull=False
            )
            
            if not completed_orders.exists():
                return 0
            
            total_days = sum([
                (o.receipt_by_maintenance - o.order_release).days
                for o in completed_orders
            ])
            
            return total_days / completed_orders.count()
            
        except Exception as e:
            print(f"Error calculating average completion time: {e}")
            return 0
    
    def _get_monthly_trends(self, today):
        """Get monthly order trends for the last 6 months"""
        try:
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
            
            monthly_data.reverse()
            return monthly_data
            
        except Exception as e:
            print(f"Error generating monthly trends: {e}")
            return []
    
    def _get_phase_analysis(self):
        """Get analysis of orders by phase"""
        try:
            return {
                'bom_ready': order.objects.filter(bom_ready__isnull=False).count(),
                'kick_off_meeting': order.objects.filter(kick_off_meeting__isnull=False).count(),
                'scaffolding_installation': order.objects.filter(scaffolding_installation__isnull=False).count(),
                'installation': order.objects.exclude(installation__isnull=True).exclude(installation__exact=[]).count(),
                'lift_handover': order.objects.filter(lift_handover__isnull=False).count(),
                'license_received': order.objects.filter(license_received__isnull=False).count(),
            }
        except Exception as e:
            print(f"Error generating phase analysis: {e}")
            return {}
    
    def _generate_alerts(self, today, last_7_days):
        """Generate alerts for the dashboard"""
        alerts = []
        
        try:
            # Orders without supervisor
            no_supervisor_count = order.objects.filter(
                supervisor__isnull=True,
                status='In Progress'
            ).count()
            
            if no_supervisor_count > 0:
                alerts.append({
                    'type': 'warning',
                    'message': f'{no_supervisor_count} orders without assigned supervisor'
                })
            
            # Overdue orders
            overdue_threshold = today - timedelta(days=90)
            overdue_orders = order.objects.filter(
                order_release__lt=overdue_threshold,
                status='In Progress'
            ).count()
            
            if overdue_orders > 0:
                alerts.append({
                    'type': 'danger',
                    'message': f'{overdue_orders} orders are overdue (>90 days)'
                })
            
            # Recent completions
            recent_completions = order.objects.filter(
                receipt_by_maintenance__gte=last_7_days
            ).count()
            
            if recent_completions > 0:
                alerts.append({
                    'type': 'success',
                    'message': f'{recent_completions} orders completed in the last 7 days'
                })
                
        except Exception as e:
            print(f"Error generating alerts: {e}")
        
        return alerts
    
    def _get_supervisor_performance(self):
        """Get supervisor performance metrics"""
        try:
            # Fixed the relationship name issue
            supervisor_performance = User.objects.filter(
                groups__name='Supervisor'
            ).annotate(
                total_orders=Count('supervisor'),
                completed_orders=Count('supervisor', filter=Q(supervisor__status='Completed'))
            ).order_by('-total_orders')[:5]
            
            # Calculate completion percentage
            for supervisor in supervisor_performance:
                supervisor.completion_percentage = (
                    supervisor.completed_orders / supervisor.total_orders * 100
                    if supervisor.total_orders > 0 else 0
                )
            
            return supervisor_performance
            
        except Exception as e:
            print(f"Error getting supervisor performance: {e}")
            return []



##################################################################################################################################
##################################################################################################################################

class UserPasswordChangeView(PasswordChangeView):
    """
    Handles the user password change process.
    - Uses the custom form for styling.
    - Specifies the template to render.
    - Redirects to the dashboard on success.
    """
    template_name = 'change_password.html'
    form_class = UserPasswordChangeForm
    success_url = reverse_lazy('dashboard') # Redirect to your dashboard after a successful change

##################################################################################################################################
##################################################################################################################################

@login_required
def export_orders_xls(request):
    orders = order.objects.all().order_by('-order_release')

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="orders.xlsx"'

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = 'Orders'

    # Define your headers based on your table columns in order_list.html
    headers = [
        "Order Number", "Equipment No.", "Agreement No.", "Site Name", "Block", "Lift No.", "Lift Qty",
        "Sales Executive", "Supervisor", "Order Release", "Supervisor Decided", "BOM Ready",
        "GAD Send for Sign", "Kick Off Meeting", "Scaffolding Message", "Scaffolding Delivery",
        "Erector File Ready", "Scaffolding Installation", "Reading Receipt", "PO Release",
        "Material Dump", "Installation", "Lift Handover", "GAD Sign Complete", "Form A Submitted",
        "Form A Permission Received", "Form B Submitted", "License Received", "License Handover",
        "Handover OC Submitted", "Email to Maintenance", "Receipt by Maintenance", "Status"
    ]
    worksheet.append(headers)

    # Populate data rows
    for ord_obj in orders:
        sales_executive_name = ord_obj.sales_executive.get_full_name() or ord_obj.sales_executive.username if ord_obj.sales_executive else ""
        supervisor_name = ord_obj.supervisor.get_full_name() if ord_obj.supervisor else ""

        # Handle JSON fields for PO Release and Material Dump
        po_release_data = ""
        if ord_obj.po_release and isinstance(ord_obj.po_release, list):
            po_release_data = "; ".join([f"{item.get('date', '')} - {item.get('percentage', '')}" for item in ord_obj.po_release])

        material_dump_data = ""
        if ord_obj.material_dump and isinstance(ord_obj.material_dump, list):
            material_dump_data = "; ".join([f"{item.get('date', '')} - {item.get('percentage', '')}" for item in ord_obj.material_dump])
        installation_data = ""
        if ord_obj.installation and isinstance(ord_obj.installation, list):
            installation_data = "; ".join([f"{item.get('date', '')} - {item.get('percentage', '')}" for item in ord_obj.installation])

        row_data = [
            ord_obj.order_number,
            ord_obj.equipment_number or "",
            ord_obj.agreement_number or "",
            ord_obj.site_name or "",
            ord_obj.block or "",
            ord_obj.lift_number or "",
            ord_obj.lift_quantity or "",
            sales_executive_name,
            supervisor_name,
            ord_obj.order_release.strftime("%Y-%m-%d") if ord_obj.order_release else "",
            ord_obj.supervisor_decided.strftime("%Y-%m-%d") if ord_obj.supervisor_decided else "",
            ord_obj.bom_ready.strftime("%Y-%m-%d") if ord_obj.bom_ready else "",
            ord_obj.gad_send_for_sign.strftime("%Y-%m-%d") if ord_obj.gad_send_for_sign else "",
            ord_obj.kick_off_meeting.strftime("%Y-%m-%d") if ord_obj.kick_off_meeting else "",
            ord_obj.scaffolding_message.strftime("%Y-%m-%d") if ord_obj.scaffolding_message else "",
            ord_obj.scaffolding_delivery.strftime("%Y-%m-%d") if ord_obj.scaffolding_delivery else "",
            ord_obj.erector_file_ready.strftime("%Y-%m-%d") if ord_obj.erector_file_ready else "",
            ord_obj.scaffolding_installation.strftime("%Y-%m-%d") if ord_obj.scaffolding_installation else "",
            ord_obj.reading_receipt.strftime("%Y-%m-%d") if ord_obj.reading_receipt else "",
            po_release_data,
            material_dump_data,
            installation_data,
            ord_obj.lift_handover.strftime("%Y-%m-%d") if ord_obj.lift_handover else "",
            ord_obj.gad_sign_complete.strftime("%Y-%m-%d") if ord_obj.gad_sign_complete else "",
            ord_obj.form_a_submitted.strftime("%Y-%m-%d") if ord_obj.form_a_submitted else "",
            ord_obj.form_a_permission_received.strftime("%Y-%m-%d") if ord_obj.form_a_permission_received else "",
            ord_obj.form_b_submitted.strftime("%Y-%m-%d") if ord_obj.form_b_submitted else "",
            ord_obj.license_received.strftime("%Y-%m-%d") if ord_obj.license_received else "",
            ord_obj.license_handover.strftime("%Y-%m-%d") if ord_obj.license_handover else "",
            ord_obj.handover_oc_submitted.strftime("%Y-%m-%d") if ord_obj.handover_oc_submitted else "",
            ord_obj.email_to_maintenance.strftime("%Y-%m-%d") if ord_obj.email_to_maintenance else "",
            ord_obj.receipt_by_maintenance.strftime("%Y-%m-%d") if ord_obj.receipt_by_maintenance else "",
            ord_obj.status or ""
        ]
        worksheet.append(row_data)

    workbook.save(response)
    return response
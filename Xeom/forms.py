from django import forms
from django.contrib.auth.models import User, Group
from .models import order
import json, datetime
from collections import OrderedDict
from django.core.exceptions import ValidationError
from django.forms.widgets import MultiWidget, TextInput, NumberInput, DateInput, Widget
from django.forms.fields import MultiValueField, CharField, IntegerField, DateField, DecimalField, Field

# --- Date field validation for restricting today -3 days ---

class ValidatedDateInput(forms.DateInput):
    """
    A custom DateInput widget that automatically sets min/max attributes for
    client-side validation to allow dates from today up to 3 days prior,
    and sets today's date as the default value if the field is empty.
    """
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}

        today = datetime.date.today()
        three_days_ago = today - datetime.timedelta(days=3)

        # Set HTML5 min and max attributes for client-side validation
        attrs['type'] = 'date' # Ensure it's a date picker
        attrs['max'] = today.strftime('%Y-%m-%d')
        attrs['min'] = three_days_ago.strftime('%Y-%m-%d')

        super().__init__(attrs)

    # def get_context(self, name, value, attrs):
    #     # If the field has no existing value, set the default to today's date
    #     if value is None or value == '':
    #         today = datetime.date.today()
    #         value = today.strftime('%Y-%m-%d')
    #     return super().get_context(name, value, attrs)

# Custom Widget for JSONField to render a list of JSONListItemWidgets
class JSONListWidget(forms.widgets.Widget):
    """
    A custom widget for Django's JSONField that allows adding/removing
    rows of SL No, Date, and Percentage inputs, storing them as a JSON list.
    """
    template_name = 'widgets/json_list_widget.html'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        
        # Ensure value is a list (even if empty or None).
        # This handles cases where the DB might store None, or a single dict (user's request).
        if not isinstance(value, list):
            if value is None:
                value = []
            elif isinstance(value, dict): # If it's a single dict, wrap it in a list
                value = [value]
            else: # Attempt to load from JSON string
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        value = parsed_value
                    elif isinstance(parsed_value, dict): # If parsed value is a single dict, wrap it
                        value = [parsed_value]
                    else:
                        value = [] # Fallback for unexpected format
                except (json.JSONDecodeError, TypeError):
                    value = []

        context['widget']['initial_forms'] = value # Pass the list of dictionaries to the template
        
        # Add a dedicated boolean flag for readonly status to the context
        context['widget']['is_readonly'] = attrs.get('data-readonly', 'false') == 'true'

        # Ensure the value for the hidden input is a JSON string, defaulting to '[]' if empty
        if not value and not context['widget']['is_readonly']:
            context['widget']['value'] = '[]'
        else:
            context['widget']['value'] = json.dumps(value)

        return context

    def value_from_datadict(self, data, files, name):
        """
        Processes the incoming POST data to reconstruct the JSON list.
        """
        items = []
        # Iterate through submitted data to find all items for this field
        i = 0
        while True:
            sl_no_key = f"{name}_item_{i}_sl_no"
            date_key = f"{name}_item_{i}_date"
            percentage_key = f"{name}_item_{i}_percentage"

            # Check if any part of the item exists in the submitted data
            if sl_no_key in data or date_key in data or percentage_key in data:
                sl_no = data.get(sl_no_key)
                date = data.get(date_key)
                percentage = data.get(percentage_key)

                # Convert to appropriate types, handling potential empty strings
                try:
                    sl_no = int(sl_no) if sl_no else None
                except ValueError:
                    sl_no = None
                
                try:
                    percentage = float(percentage) if percentage else None
                except ValueError:
                    percentage = None

                # Only add item if at least one field has a value
                if sl_no is not None or date or percentage is not None:
                    items.append({
                        'sl_no': sl_no,
                        'date': date,
                        'percentage': percentage,
                    })
                i += 1
            else:
                break # No more items found

        return json.dumps(items) # Return as JSON string

# Custom Form Field for JSONField
class JSONListField(forms.Field):
    """
    A custom form field for Django's JSONField that uses JSONListWidget.
    Handles validation for the list of dictionaries.
    """
    widget = JSONListWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        """
        Converts the JSON string from the widget back into a Python list of dicts.
        """
        if isinstance(value, list): # Already a list (e.g., from initial data)
            return value
        if value is None or value == '' or value == '[]':
            return []
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                # If it's a single dictionary (due to default={})
                # and we expect a list, wrap it.
                if isinstance(parsed, dict):
                    return [parsed]
                raise ValidationError("Invalid JSON format for JSONListField: expected a list.")
            return parsed
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format for JSONListField.")

    def validate(self, value):
        super().validate(value)
        if not isinstance(value, list):
            raise ValidationError("Expected a list of items.")
        for item in value:
            if not isinstance(item, dict):
                raise ValidationError("Each item in the list must be a dictionary.")
            # Add more specific validation for 'sl_no', 'date', 'percentage' if needed
            # For example, checking types or ranges
            if 'sl_no' in item and item['sl_no'] is not None and not isinstance(item['sl_no'], int):
                raise ValidationError("SL No. must be an integer.")
            if 'percentage' in item and item['percentage'] is not None and not isinstance(item['percentage'], (int, float)):
                raise ValidationError("Percentage must be a number.")
            if 'date' in item and item['date'] is not None:
                try:
                    if item['date'] != "":
                        datetime.date.fromisoformat(item['date'])
                except ValueError:
                    raise ValidationError("Date must be in YYYY-MM-DD format.")
        total_percentage = 0
        for item in value:
            total_percentage = item['percentage'] + total_percentage
            if total_percentage > 100:
                raise ValidationError("Total percentage cannot exceed 100% across all items.")
            

# --- Existing Forms (with updates for JSON fields) ---
class OrderCreateForm(forms.ModelForm):
    """
    Form for creating a new Order.
    Includes only essential fields for initial order creation.
    """
    class Meta:
        model = order
        # Fields to show for a new order creation
        fields = [
            'order_number',
            'equipment_number',
            'agreement_number',
            'site_name',
            'block',
            'lift_number',
            'lift_quantity',
            'sales_executive',
            # Other initial fields that are not part of the sequential workflow dates
        ]
        widgets = {
            'order_number': forms.TextInput(attrs={'class': 'form-control'}),
            'equipment_number': forms.TextInput(attrs={'class': 'form-control'}),
            'agreement_number': forms.TextInput(attrs={'class': 'form-control'}),
            'site_name': forms.TextInput(attrs={'class': 'form-control'}),
            'block': forms.TextInput(attrs={'class': 'form-control'}),
            'lift_number': forms.TextInput(attrs={'class': 'form-control'}),
            'lift_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'sales_executive': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate sales_executive dropdown with active users
        # You might want to filter users by a specific 'Sales' role if roles are defined
        self.fields['sales_executive'].queryset = User.objects.filter(groups__name='Sales Person',is_active=True)
        # Example of setting initial values or making fields required based on logic
        for field_name, field in self.fields.items():
            field.required = True # Make all initial fields required by default
            if isinstance(field.widget, forms.TextInput) or isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({'class': 'form-control'})

class OrderDetailForm(forms.ModelForm):
    # Custom fields for JSON data
    po_release = JSONListField(required=False, label="PO Release Stages")
    material_dump = JSONListField(required=False, label="Material Dump Stages")
    installation = JSONListField(required=False, label="Installation Stages")
    #erector = forms.ChoiceField(choices=[('SOVANJI','SOVANJI'),('PRAVINBHAI','PRAVINBHAI'),('ROSHANBHAI','ROSHANBHAI'),('BHAVESHBHAI','BHAVESHBHAI'),('JATINBHAI','JATINBHAI'),('DIPAKBHAI','DIPAKBHAI'),('KIRANBHAI','KIRANBHAI'),('MUNAVARBHAI','MUNAVARBHAI'),('KAUSHIKBHAI','KAUSHIKBHAI'),('RAJU','RAJU'),('ASHOKBHAI','ASHOKBHAI'),('OM PRAKASH','OM PRAKASH')], widget=forms.Select(attrs={'class': 'form-select'}))
    class Meta:
        model = order
        basic_fields = [
            'order_number', 'equipment_number', 'agreement_number', 'site_name',
            'block', 'lift_number', 'lift_quantity', 'sales_executive'
        ]
        add_fields = [
            'order_release', 'supervisor' ,'supervisor_decided', 'bom_ready', 'gad_send_for_sign',
            'kick_off_meeting', 'scaffolding_message', 'scaffolding_delivery','erector', 'erector_decided',
            'erector_file_ready', 'scaffolding_installation', 'reading_receipt',
            'installation', 'lift_handover', 'gad_sign_complete', 'form_a_submitted',
            'form_a_permission_received', 'form_b_submitted', 'license_received',
            'license_handover', 'handover_oc_submitted', 'email_to_maintenance',
            'receipt_by_maintenance', 'status'
        ]
        fields = basic_fields + add_fields + ['po_release', 'material_dump','installation']

        widgets = {
            'order_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter order number',  'readonly': True}),
            'equipment_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter equipment number', 'readonly': True}),
            'agreement_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter agreement number','readonly': True}),
            'site_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter site name',  'readonly': True}),
            'block': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter block', 'readonly': True}),
            'lift_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter lift number', 'readonly': True}),
            'lift_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'readonly': True}),
            'sales_executive': forms.Select(attrs={'class': 'form-select', 'disabled': True}),
            'supervisor': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select','readonly': True}),

            # Date fields - all set to type 'date' for HTML5 date picker
            'order_release': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supervisor_decided': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bom_ready': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gad_send_for_sign': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kick_off_meeting': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_message': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_delivery': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'erector': forms.Select(attrs={'class':'form-select','placeholder':'Select Ecrector'}),
            'erector_decided': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'erector_file_ready': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_installation': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reading_receipt': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            #'installation': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'lift_handover': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gad_sign_complete': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_a_submitted': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_a_permission_received': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_b_submitted': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'license_received': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'license_handover': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'handover_oc_submitted': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'email_to_maintenance': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'receipt_by_maintenance': ValidatedDateInput(attrs={'class': 'form-control', 'type': 'date'}),
            # IMPORTANT: The 'po_release' and 'material_dump' entries must NOT be here
            # because they are already defined as JSONListField class attributes above.
            # Example (REMOVE THESE LINES IF THEY EXIST):
            # 'po_release': JSONListField(required=False, label="PO Release Stages"),
            # 'material_dump': JSONListField(required=False, label="Material Dump Stages")
        }

    # Define group-to-field mappings for activities
    GROUP_ACTIVITY_MAPPING = {
        'Admin': ['order_release', 'email_to_maintenance'],
        'Supervisor HOD': ['supervisor','supervisor_decided'],
        'Supervisor': ['kick_off_meeting', 'scaffolding_message', 'scaffolding_installation',
                       'installation', 'lift_handover', 'gad_sign_complete'],
        'Designer': ['erector','erector_decided','erector_file_ready', 'reading_receipt', 'bom_ready', 'gad_send_for_sign'],
        'Store manager': ['scaffolding_delivery'],
        'Purchase manager': ['po_release', 'material_dump'], # These will now use the custom field
        'License Consultant': ['form_a_submitted', 'form_a_permission_received', 'form_b_submitted', 'license_received'],
        'Sales person': ['license_handover', 'handover_oc_submitted'],
        'Maintenance HOD': ['receipt_by_maintenance']
    }

    # Define workflow dependencies based on the flowchart
    WORKFLOW_DEPENDENCIES = {
        'order_release': [],
        'supervisor_decided': ['order_release'],
        'erector':['order_release'],
        'erector_decided':['order_release'],
        'erector_file_ready': ['erector_decided'],
        'bom_ready': ['order_release'],
        'gad_send_for_sign': ['order_release'],
        'kick_off_meeting': ['supervisor_decided'],
        'scaffolding_message': ['kick_off_meeting'],
        'scaffolding_delivery': ['scaffolding_message'],
        'po_release': ['bom_ready'],
        'material_dump': ['po_release'],
        'gad_sign_complete': ['gad_send_for_sign'],
        'form_a_submitted': ['gad_sign_complete'],
        'form_a_permission_received': ['form_a_submitted'],
        'form_b_submitted': ['form_a_permission_received'],
        'license_received': ['form_b_submitted'],
        'scaffolding_installation': ['scaffolding_delivery', 'erector_file_ready'],
        'reading_receipt': ['scaffolding_installation'],
        'installation': ['reading_receipt', 'material_dump'],
        'lift_handover': ['installation'],
        'license_handover': ['lift_handover', 'license_received'],
        'handover_oc_submitted': ['license_handover'],
        'email_to_maintenance': ['handover_oc_submitted'],
        'receipt_by_maintenance': ['email_to_maintenance'],
    }

    # User-friendly display names for fields, used in error messages
    FIELD_DISPLAY_NAMES = {
        'order_number': 'Order Number',
        'equipment_number': 'Equipment Number',
        'agreement_number': 'Agreement Number',
        'site_name': 'Site Name',
        'block': 'Block',
        'lift_number': 'Lift Number',
        'lift_quantity': 'Lift Quantity',
        'sales_executive': 'Sales Executive',
        'supervisor': 'Supervisor',
        'status': 'Status',
        'order_release': 'Order Release',
        'supervisor_decided': 'Supervisor Decided',
        'erector':'Erector Partner',
        'erector_decided': 'Erector Decided',
        'erector_file_ready': 'Erector File Ready',
        'bom_ready': 'BOM Ready',
        'gad_send_for_sign': 'GAD Send for Sign',
        'kick_off_meeting': 'Kick-off Meeting',
        'scaffolding_message': 'Scaffolding Message',
        'scaffolding_delivery': 'Scaffolding Delivery',
        'scaffolding_installation': 'Scaffolding Installation',
        'reading_receipt': 'Reading Receipt',
        'po_release': 'PO Release Stages', # Updated display name
        'material_dump': 'Material Dump Stages', # Updated display name
        'installation': 'Installation',
        'lift_handover': 'Lift Handover',
        'gad_sign_complete': 'GAD Sign Complete',
        'form_a_submitted': 'A Form Submitted',
        'form_a_permission_received': 'A Form Permission Received',
        'form_b_submitted': 'B Form Submitted',
        'license_received': 'License Received',
        'license_handover': 'License Handover',
        'handover_oc_submitted': 'Handover OC Submitted',
        'email_to_maintenance': 'Email to Maintenance',
        'receipt_by_maintenance': 'Receipt by Maintenance',
    }

    # Fields that are always visible (basic order info)
    BASIC_INFO_FIELDS = [
        'order_number', 'equipment_number', 'agreement_number',
        'site_name', 'block', 'lift_number', 'lift_quantity',
        #'sales_executive', 'supervisor', 'status',
    ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.fields['sales_executive'].queryset = User.objects.filter(groups__name='Sales Person',is_active=True)
        self.fields['supervisor'].queryset = User.objects.filter(groups__name='Supervisor',is_active=True)

        if self.user:
            self._apply_field_permissions_and_workflow_state()

        # For JSONListField, ensure initial data is passed correctly to the widget
        # The widget's get_context handles the parsing from JSON string to Python list
        # when the form is initialized with an existing instance.
        if self.instance and self.instance.pk:
            if self.instance.po_release:
                self.initial['po_release'] = json.dumps(self.instance.po_release)
            if self.instance.material_dump:
                self.initial['material_dump'] = json.dumps(self.instance.material_dump)
            if self.instance.installation:
                self.initial['installation'] = json.dumps(self.instance.installation)
            
    def _apply_field_permissions_and_workflow_state(self):
        user_groups = self.user.groups.values_list('name', flat=True)
        user_allowed_activity_fields = set()

        for group_name in user_groups:
            if group_name in self.GROUP_ACTIVITY_MAPPING:
                user_allowed_activity_fields.update(self.GROUP_ACTIVITY_MAPPING[group_name])

        # Create a list of field names that should be present in the final form, in order
        final_field_names_in_order = []

        # Add basic info fields first
        for f_name in self.BASIC_INFO_FIELDS:
            if f_name in self.fields:
                final_field_names_in_order.append(f_name)

        # Add activity fields based on permissions
        all_meta_fields = list(self._meta.fields)
        
        for f_name in all_meta_fields:
            if f_name in self.BASIC_INFO_FIELDS:
                continue # Already handled

            if f_name in user_allowed_activity_fields:
                if f_name not in final_field_names_in_order: # Prevent duplicates
                    final_field_names_in_order.append(f_name)

        # Add supervisor and status explicitly after basic fields and before other activities if not already added
        # if 'supervisor' in self.fields and 'supervisor' not in final_field_names_in_order:
        #     final_field_names_in_order.append('supervisor')
        # if 'status' in self.fields and 'status' not in final_field_names_in_order:
        #     final_field_names_in_order.append('status')

        # Now, reconstruct self.fields to reflect the desired order and visibility
        ordered_fields = OrderedDict()
        for field_name in final_field_names_in_order:
            if field_name in self.fields:
                ordered_fields[field_name] = self.fields[field_name]

        self.fields = ordered_fields

        # Finally, apply the editable states to the fields that are now in the form
        for field_name, bound_field in self.fields.items():
            if field_name in self.BASIC_INFO_FIELDS:
                bound_field.widget.attrs['readonly'] = True
                bound_field.widget.attrs['style'] = 'background-color: #e9ecef; cursor: not-allowed;'
                if isinstance(bound_field.widget, forms.Select):
                    bound_field.widget.attrs['disabled'] = True

            elif field_name in user_allowed_activity_fields:
                field_value = getattr(self.instance, field_name)
                
                # Special handling for JSONListField: editable if empty AND prerequisites met
                if field_name in ['po_release', 'material_dump','installation']:
                    # Field is editable if its current value (list) is empty, AND prerequisites are met
                    # Note: an empty list [] evaluates to False, so 'not field_value' works here.
                    is_editable = not field_value and self._are_prerequisites_met(field_name)
                    self._set_field_editable_state(bound_field, not is_editable) # Set readonly to opposite of is_editable
                else:
                    # For other activity fields (like date fields), it's editable if no value exists and prerequisites are met
                    is_editable = not field_value and self._are_prerequisites_met(field_name)
                    self._set_field_editable_state(bound_field, not is_editable) # Set readonly to opposite of is_editable
            else:
                # Fields not in basic info and not allowed by user groups should be readonly
                self._set_field_editable_state(bound_field, True)

    def _are_prerequisites_met(self, field_name):
        prerequisites = self.WORKFLOW_DEPENDENCIES.get(field_name, [])
        if not prerequisites:
            return True # No prerequisites, so met

        for prereq in prerequisites:
            # Get the actual value from the model instance
            prereq_value = getattr(self.instance, prereq, None)
            
            # Special handling for JSONListField prerequisites
            if prereq in ['po_release', 'material_dump']:
                # If a JSONListField is a prerequisite, it must contain data (i.e., not be an empty list)
                if not prereq_value or (isinstance(prereq_value, list) and not prereq_value):
                    return False
            elif not prereq_value: # For other field types, check if value exists
                return False
        return True

    def _set_field_editable_state(self, bound_field, make_readonly):
        if make_readonly:
            bound_field.widget.attrs['readonly'] = True
            bound_field.widget.attrs['style'] = 'background-color: #e9ecef; cursor: not-allowed;'
            # For Select widgets, 'disabled' is used instead of 'readonly'
            if isinstance(bound_field.widget, forms.Select):
                bound_field.widget.attrs['disabled'] = True
            # For JSONListWidget, hide add/remove buttons if readonly
            if isinstance(bound_field.widget, JSONListWidget):
                bound_field.widget.attrs['readonly'] = True # Pass readonly to the widget for template logic
        else:
            if 'readonly' in bound_field.widget.attrs:
                del bound_field.widget.attrs['readonly']
            if 'style' in bound_field.widget.attrs:
                # Remove style only if it's the specific readonly style
                if 'background-color: #e9ecef; cursor: not-allowed;' in bound_field.widget.attrs['style']:
                    bound_field.widget.attrs['style'] = bound_field.widget.attrs['style'].replace('background-color: #e9ecef; cursor: not-allowed;', '').strip()
            if 'disabled' in bound_field.widget.attrs:
                del bound_field.widget.attrs['disabled']
            if isinstance(bound_field.widget, JSONListWidget):
                bound_field.widget.attrs.pop('readonly', None)

    def clean(self):
        cleaned_data = super().clean()
        
        user_groups = self.user.groups.values_list('name', flat=True)
        user_allowed_activity_fields = set()
        for group_name in user_groups:
            if group_name in self.GROUP_ACTIVITY_MAPPING:
                user_allowed_activity_fields.update(self.GROUP_ACTIVITY_MAPPING[group_name])

        # Validate permissions and workflow dependencies
        for field_name, value in list(cleaned_data.items()):
            # Skip fields that are not in the form's visible fields (i.e., not added by _apply_field_permissions_and_workflow_state)
            if field_name not in self.fields:
                continue

            # Get the original value from the instance to check for modifications
            original_value = getattr(self.instance, field_name, None)

            # Convert original_value for JSONListFields to a comparable format
            if field_name in ['po_release', 'material_dump']:
                if original_value is None:
                    original_value_comparable = []
                elif isinstance(original_value, str):
                    try:
                        original_value_comparable = json.loads(original_value)
                    except json.JSONDecodeError:
                        original_value_comparable = []
                else: # Assume it's already a list or other comparable format
                    original_value_comparable = original_value
                
                # Convert submitted value for JSONListFields to a comparable format
                if isinstance(value, str):
                    try:
                        value_comparable = json.loads(value)
                    except json.JSONDecodeError:
                        value_comparable = []
                else:
                    value_comparable = value # Assume it's already a list
            else:
                original_value_comparable = original_value
                value_comparable = value

            if field_name not in self.BASIC_INFO_FIELDS and field_name not in user_allowed_activity_fields:
                # If the field is not a basic info field and user is not allowed to interact
                # Check if the user tried to change a field they shouldn't
                if value_comparable != original_value_comparable:
                    self.add_error(field_name, f"You do not have permission to modify '{self.FIELD_DISPLAY_NAMES.get(field_name, field_name)}'.")
                    continue

            # Workflow dependency validation for fields the user is allowed to fill
            if field_name in user_allowed_activity_fields:
                # If the field is being set/updated and was previously empty or not existing
                if value and (original_value_comparable is None or original_value_comparable == []): # Check for both None and empty list for JSONListField
                    if not self._are_prerequisites_met(field_name):
                        prerequisites = self.WORKFLOW_DEPENDENCIES.get(field_name, [])
                        missing_prereqs_display_names = []
                        for prereq in prerequisites:
                            # Check if the prerequisite field exists and has a value
                            prereq_value = getattr(self.instance, prereq, None)
                            if prereq in ['po_release', 'material_dump']:
                                if not prereq_value or (isinstance(prereq_value, list) and not prereq_value):
                                    missing_prereqs_display_names.append(self.FIELD_DISPLAY_NAMES.get(prereq, prereq))
                            elif not prereq_value:
                                missing_prereqs_display_names.append(self.FIELD_DISPLAY_NAMES.get(prereq, prereq))

                        if missing_prereqs_display_names:
                            current_field_display_name = self.FIELD_DISPLAY_NAMES.get(field_name, field_name)
                            error_message = (
                                f"Cannot complete '{current_field_display_name}' before completing: "
                                f"{', '.join(missing_prereqs_display_names)}."
                            )
                            self.add_error(field_name, error_message)
        return cleaned_data

    def get_field_display_name(self, field_name):
        return self.FIELD_DISPLAY_NAMES.get(field_name, field_name)


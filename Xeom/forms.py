from django import forms
from django.contrib.auth.models import User, Group
from .models import order
import json
from collections import OrderedDict
from django.core.exceptions import ValidationError
from django.forms.widgets import MultiWidget, TextInput, NumberInput, DateInput
from django.forms.fields import MultiValueField, CharField, IntegerField, DateField, DecimalField

# --- Custom Widgets and Fields for JSON List Data ---

class JSONListItemWidget(MultiWidget):
    """
    A widget to render a single item (sl_no, date, percentage) for the JSON list.
    """
    def __init__(self, attrs=None):
        widgets = [
            NumberInput(attrs={'class': 'form-control form-control-sm json-sl-no', 'placeholder': 'SL No.', 'min': '1'}),
            DateInput(attrs={'class': 'form-control form-control-sm json-date', 'type': 'date'}),
            NumberInput(attrs={'class': 'form-control form-control-sm json-percentage', 'placeholder': 'Percentage', 'min': '0', 'max': '100'}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        # Decompress a single dictionary item into a list of values for each sub-widget
        if value:
            return [value.get('sl_no'), value.get('date'), value.get('percentage')]
        return [None, None, None]

class JSONListWidget(MultiWidget):
    """
    A widget to render a dynamic list of JSONListItemWidgets.
    This widget is primarily a container; the dynamic adding/removing of items
    will be handled by JavaScript in the template.
    """
    template_name = 'widgets/json_list_widget.html' # Custom template for rendering

    def __init__(self, attrs=None):
        # This widget doesn't need to define sub-widgets directly here
        # as it will be rendered by a custom template that handles dynamic items.
        super().__init__([], attrs) # Pass an empty list of widgets

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Value will be the JSON string from the model.
        # We need to parse it and prepare it for rendering.
        try:
            parsed_value = json.loads(value) if value else []
        except (json.JSONDecodeError, TypeError):
            parsed_value = [] # Fallback for invalid JSON or non-string value

        # Prepare initial forms for existing data
        initial_forms = []
        for i, item in enumerate(parsed_value):
            # Create a dummy form for each item to leverage Django's widget rendering
            # This is a bit of a hack, but allows us to use decompress logic
            item_widget = JSONListItemWidget()
            item_data = item_widget.decompress(item)
            # Manually create the HTML for each item using its sub-widgets
            # This part is tricky to do purely in Python for dynamic lists.
            # We'll rely more heavily on the template to iterate and render.
            initial_forms.append({
                'sl_no': item.get('sl_no', ''),
                'date': item.get('date', ''),
                'percentage': item.get('percentage', ''),
            })
        context['widget']['initial_forms'] = initial_forms
        return context


class JSONListField(forms.Field):
    """
    A custom form field for handling a list of structured JSON objects.
    It expects data in the format:
    [
        {"sl_no": 1, "date": "YYYY-MM-DD", "percentage": 50},
        {"sl_no": 2, "date": "YYYY-MM-DD", "percentage": 30}
    ]
    """
    widget = JSONListWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These are the fields for a single item.
        # We'll validate each item's structure here.
        self.item_fields = {
            'sl_no': IntegerField(required=True, min_value=1),
            'date': DateField(required=True),
            'percentage': DecimalField(required=True, min_value=0, max_value=100),
        }

    def to_python(self, value):
        """
        Converts the incoming data from the widget (which will be a list of lists/dicts
        from the dynamically added fields) into the Python list of dictionaries.
        """
        if not value:
            return []

        # Value will be a list of dictionaries, where each dict represents a row
        # and its keys are 'sl_no', 'date', 'percentage'
        if not isinstance(value, list):
            raise ValidationError("Invalid data format. Expected a list of items.")

        cleaned_data = []
        total_percentage = 0

        for i, item_data in enumerate(value):
            if not isinstance(item_data, dict):
                raise ValidationError(f"Item {i+1} is not a valid object.")

            item_sl_no = item_data.get('sl_no')
            item_date = item_data.get('date')
            item_percentage = item_data.get('percentage')

            # Validate each sub-field
            try:
                sl_no = self.item_fields['sl_no'].clean(item_sl_no)
                date = self.item_fields['date'].clean(item_date)
                percentage = self.item_fields['percentage'].clean(item_percentage)
            except ValidationError as e:
                # Add specific error to the item
                raise ValidationError(f"Item {i+1} has an error: {e.message}")

            cleaned_data.append({
                'sl_no': sl_no,
                'date': date.strftime('%Y-%m-%d'), # Ensure date is formatted consistently
                'percentage': float(percentage), # Store as float for JSONField
            })
            total_percentage += float(percentage)

        if total_percentage > 100:
            raise ValidationError(f"Total percentage cannot exceed 100%. Current total: {total_percentage}%.")

        return cleaned_data

    def validate(self, value):
        super().validate(value)
        # Additional validation for the list of items (e.g., uniqueness of sl_no)
        sl_nos = set()
        for i, item in enumerate(value):
            sl_no = item.get('sl_no')
            if sl_no in sl_nos:
                raise ValidationError(f"Duplicate SL No. '{sl_no}' found for item {i+1}.")
            sl_nos.add(sl_no)


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
    """
    Django Form for the Order model, with dynamic field visibility,
    editability, and workflow validation based on the logged-in user's
    group and the current state of the order workflow.
    """
    # Use the custom JSONListField for these fields
    po_release = JSONListField(required=False, label="PO Release Stages")
    material_dump = JSONListField(required=False, label="Material Dump Stages")

    class Meta:
        model = order
        # Explicitly list all fields here. This gives us full control.
        # Even if we want to hide most, defining them here makes them available in self.base_fields.
        basic_fields = [
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
        
        add_fields = [
            'supervisor', 
            'order_release', 'supervisor_decided', 'bom_ready',
            'gad_send_for_sign', 'kick_off_meeting', 'scaffolding_message',
            'scaffolding_delivery', 'erector_file_ready', 'scaffolding_installation',
            'reading_receipt', 'installation', 'lift_handover',
            'gad_sign_complete', 'form_a_submitted', 'form_a_permission_received',
            'form_b_submitted', 'license_received', 'license_handover',
            'handover_oc_submitted', 'email_to_maintenance', 'receipt_by_maintenance',
            # 'po_release', 'material_dump', # These are now defined as custom fields above
            'status',
        ]
        fields = basic_fields + add_fields + ['po_release', 'material_dump'] # Add custom fields to the list


        widgets = {
            'order_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter order number',  'readonly': True}),
            'equipment_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter equipment number', 'readonly': True}),
            'agreement_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter agreement number','readonly': True}),
            'site_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter site name',  'readonly': True}),
            'block': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter block', 'readonly': True}),
            'lift_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter lift number', 'readonly': True}),
            'lift_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'readonly': True}),
            'sales_executive': forms.Select(attrs={'class': 'form-select', 'readonly': True}),
            'supervisor': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select','readonly': True}),

            # Date fields - all set to type 'date' for HTML5 date picker
            'order_release': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supervisor_decided': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bom_ready': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gad_send_for_sign': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kick_off_meeting': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_message': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_delivery': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'erector_file_ready': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'scaffolding_installation': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reading_receipt': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'installation': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'lift_handover': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gad_sign_complete': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_a_submitted': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_a_permission_received': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'form_b_submitted': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'license_received': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'license_handover': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'handover_oc_submitted': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'email_to_maintenance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'receipt_by_maintenance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),

            # Removed custom widgets for po_release and material_dump from here,
            # as they are now defined as custom fields above.
        }

    # Define group-to-field mappings for activities
    GROUP_ACTIVITY_MAPPING = {
        'Admin': ['order_release', 'email_to_maintenance'],
        'Supervisor HOD': ['supervisor_decided','supervisor'],
        'Supervisor': ['kick_off_meeting', 'scaffolding_message', 'scaffolding_installation',
                       'installation', 'lift_handover', 'gad_sign_complete'],
        'Designer': ['erector_file_ready', 'reading_receipt', 'bom_ready', 'gad_send_for_sign'],
        'Store manager': ['scaffolding_delivery'],
        'Purchase manager': ['po_release', 'material_dump'], # These will now use the custom field
        'Licence Consultant': ['form_a_submitted', 'form_a_permission_received', 'form_b_submitted', 'license_received'],
        'Sales person': ['license_handover', 'handover_oc_submitted'],
        'Maintenance HOD': ['receipt_by_maintenance']
    }

    # Define workflow dependencies based on the flowchart
    WORKFLOW_DEPENDENCIES = {
        'order_release': [],
        'supervisor_decided': ['order_release'],
        'erector_file_ready': ['order_release'],
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
        'sales_executive',
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
        # Iterate over all fields defined in Meta, including the custom ones
        all_meta_fields = list(self._meta.fields) + ['po_release', 'material_dump']
        for f_name in all_meta_fields:
            if f_name in self.BASIC_INFO_FIELDS:
                continue # Already handled

            if f_name in user_allowed_activity_fields:
                final_field_names_in_order.append(f_name)

        # Now, reconstruct self.fields to reflect the desired order and visibility
        # We preserve the BoundField instances from the original self.fields
        ordered_fields = OrderedDict()
        for field_name in final_field_names_in_order:
            if field_name in self.fields: # Check if the BoundField exists
                ordered_fields[field_name] = self.fields[field_name]

        self.fields = ordered_fields # Replace the form's fields OrderedDict

        # Finally, apply the editable states to the fields that are now in the form
        for field_name, bound_field in self.fields.items():
            if field_name in self.BASIC_INFO_FIELDS:
                self._set_field_editable_state(bound_field, True)
            elif field_name in user_allowed_activity_fields:
                field_value = getattr(self.instance, field_name)
                if field_value:
                    self._set_field_editable_state(bound_field, True)
                elif not self._are_prerequisites_met(field_name):
                    self._set_field_editable_state(bound_field, True)
                else:
                    self._set_field_editable_state(bound_field, False)


    def _are_prerequisites_met(self, field_name):
        prerequisites = self.WORKFLOW_DEPENDENCIES.get(field_name)

        if prerequisites is None:
            return True

        for prereq_field in prerequisites:
            if not hasattr(self.instance, prereq_field) or not getattr(self.instance, prereq_field):
                return False
        return True

    def _set_field_editable_state(self, field, is_readonly):
        # This function now correctly receives a Field object (e.g., JSONListField, DateField)
        # and applies the readonly attribute to its widget.
        if hasattr(field.widget, 'attrs'):
            if is_readonly:
                field.widget.attrs.update({
                    'readonly': True,
                    'class': field.widget.attrs.get('class', '') + ' readonly-field',
                    'style': 'background-color: #e9ecef; cursor: not-allowed;'
                })
            else:
                field.widget.attrs.pop('readonly', None)
                field.widget.attrs.pop('disabled', None)
                current_class = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = current_class.replace('readonly-field', '').strip()
                field.widget.attrs.pop('style', None)

        if isinstance(field.widget, forms.Select):
            if is_readonly:
                field.widget.attrs.update({
                    'readonly': True,
                    'class': field.widget.attrs.get('class', '') + ' readonly-field',
                    'style': 'background-color: #e9ecef; cursor: not-allowed;'
                })
            else:
                field.widget.attrs.pop('disabled', None)
                current_class = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = current_class.replace('readonly-field', '').strip()
                field.widget.attrs.pop('style', None)

    def clean_order_number(self):
        order_number = self.cleaned_data.get('order_number')
        if order_number and not self.instance.pk:
            if order.objects.filter(order_number=order_number).exists():
                raise forms.ValidationError("This order number already exists. Please choose a unique one.")
        return order_number

    def clean(self):
        cleaned_data = super().clean()

        if self.user:
            user_groups = self.user.groups.values_list('name', flat=True)
            user_allowed_activity_fields = set()
            for group_name in user_groups:
                if group_name in self.GROUP_ACTIVITY_MAPPING:
                    user_allowed_activity_fields.update(self.GROUP_ACTIVITY_MAPPING[group_name])

            for field_name, value in self.cleaned_data.items():
                if field_name in self.BASIC_INFO_FIELDS:
                    continue

                if field_name not in user_allowed_activity_fields:
                    original_value = getattr(self.instance, field_name, None) if self.instance else None
                    # For JSONListField, the value will be a list of dicts, so compare directly
                    if field_name in ['po_release', 'material_dump']:
                        # Convert original_value from JSON string to Python list for comparison
                        original_value_parsed = json.loads(original_value) if original_value else []
                        if value and value != original_value_parsed:
                            self.add_error(field_name, f"You do not have permission to modify '{self.FIELD_DISPLAY_NAMES.get(field_name, field_name)}'.")
                            continue
                    else:
                        if value and value != original_value:
                            self.add_error(field_name, f"You do not have permission to modify '{self.FIELD_DISPLAY_NAMES.get(field_name, field_name)}'.")
                            continue

                if value and (not self.instance or not getattr(self.instance, field_name)):
                    if not self._are_prerequisites_met(field_name):
                        prerequisites = self.WORKFLOW_DEPENDENCIES.get(field_name, [])
                        missing_prereqs_display_names = []
                        for prereq in prerequisites:
                            if not hasattr(self.instance, prereq) or not getattr(self.instance, prereq):
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


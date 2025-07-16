from django.db import models
from django.contrib.auth.models import User
from simple_history.models import HistoricalRecords
from django.utils import timezone

# Create your models here.
class order(models.Model):
    order_number = models.CharField(max_length=100, primary_key=True, verbose_name="Order Number")
    equipment_number = models.CharField(max_length=100, verbose_name="Equipment Number")
    agreement_number = models.CharField(max_length=100, verbose_name="Agreement Number")
    site_name = models.CharField(max_length=100, verbose_name="Site Name")
    block = models.CharField(max_length=100, verbose_name="Block")
    lift_number = models.CharField(max_length=100, verbose_name="Lift Number")
    lift_quantity = models.IntegerField(verbose_name="Lift Quantity")
    sales_executive = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Sales Executive")
    order_release = models.DateField(verbose_name="Order Release Date", blank=True,null=True)
    supervisor_decided = models.DateField(verbose_name="Supervisor Decided Date",blank=True,null=True)
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='supervisor', verbose_name="Supervisor",blank=True,null=True)
    bom_ready = models.DateField(verbose_name="BOM Ready Date",blank=True,null=True)
    gad_send_for_sign = models.DateField(verbose_name="GAD Send for Sign Date",blank=True,null=True)
    kick_off_meeting = models.DateField(verbose_name="Kick Off Meeting Date",blank=True,null=True)
    scaffolding_message = models.DateField(verbose_name="Scaffolding Message Date",blank=True,null=True)
    scaffolding_delivery = models.DateField(verbose_name="Scaffolding Delivery Date",blank=True,null=True)
    erector = models.CharField(max_length=100, verbose_name="Erector Name", choices=[('SOVANJI','SOVANJI'),('PRAVINBHAI','PRAVINBHAI'),('ROSHANBHAI','ROSHANBHAI'),('BHAVESHBHAI','BHAVESHBHAI'),('JATINBHAI','JATINBHAI'),('DIPAKBHAI','DIPAKBHAI'),('KIRANBHAI','KIRANBHAI'),('MUNAVARBHAI','MUNAVARBHAI'),('KAUSHIKBHAI','KAUSHIKBHAI'),('RAJU','RAJU'),('ASHOKBHAI','ASHOKBHAI'),('OM PRAKASH','OM PRAKASH')],blank=True, null=True)
    erector_decided = models.DateField(verbose_name="Erector Decided Date",blank=True,null=True)
    erector_file_ready = models.DateField(verbose_name="Erector File Ready Date",blank=True,null=True)
    scaffolding_installation = models.DateField(verbose_name="Scaffolding Installation Date",blank=True,null=True)
    reading_receipt = models.DateField(verbose_name="Reading Receipt Date",blank=True,null=True)
    po_release = models.JSONField(verbose_name="PO Release", default=dict,blank=True,null=True)
    material_dump = models.JSONField(verbose_name="Material Dump", default=dict,blank=True,null=True)
    installation = models.JSONField(verbose_name="Installation Date", default=dict,blank=True,null=True)
    lift_handover = models.DateField(verbose_name="Lift Handover Date",blank=True,null=True)
    gad_sign_complete = models.DateField(verbose_name="GAD Sign Complete Date",blank=True,null=True)
    form_a_submitted = models.DateField(verbose_name="Form A Submitted Date",blank=True,null=True)
    form_a_permission_received = models.DateField(verbose_name="Form Permission Received Date",blank=True,null=True)
    form_b_submitted = models.DateField(verbose_name="Form B Submitted Date",blank=True,null=True)
    license_received = models.DateField(verbose_name="License Received Date",blank=True,null=True)
    license_handover = models.DateField(verbose_name="License Handover Date",blank=True,null=True)
    handover_oc_submitted = models.DateField(verbose_name="Handover OC Submitted Date",blank=True,null=True)
    email_to_maintenance = models.DateField(verbose_name="Email to Maintenance Date",blank=True,null=True)
    receipt_by_maintenance = models.DateField(verbose_name="Receipt by Maintenance Date",blank=True,null=True)
    status = models.CharField(max_length=100,verbose_name="Status", default="In Progress", choices=[('In Progress', 'In Progress'),('Completed', 'Completed'),])
    
    def __str__(self):
        return f"Order {self.order_number} - {self.site_name} ({self.equipment_number})"
    
    history = HistoricalRecords()

    def save(self, *args, **kwargs):   
        # Automatically mark status as 'Completed' if 'receipt_by_maintenance' is filled
        if self.erector:
            self.erector_decided = timezone.now().date()
        if self.supervisor:
            self.supervisor_decided = timezone.now().date()
        if self.order_release:
            self.status = "In Progress"
        if self.receipt_by_maintenance:
            self.status = "Completed"

        super().save(*args, **kwargs) # Call the original save method
            
    

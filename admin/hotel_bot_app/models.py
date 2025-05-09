from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class InvitedUser(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    role = ArrayField(models.CharField(max_length=100), blank=True, default=list)
    last_login = models.DateTimeField(null=True, blank=True)  # Allow null values
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=50, default='invited', null=False, blank=True)  # ✅ Add default
    password = models.BinaryField()


    def __str__(self):
        return self.name
    
    class Meta:
        db_table = "invited_users"

class Installation(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room = models.IntegerField(null=True, blank=True)
    product_available = models.TextField(null=True, blank=True)
    prework = models.TextField(null=True, blank=True)
    prework_checked_by = models.ForeignKey(
        InvitedUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='prework_checked_by'
    )
    prework_check_on = models.DateTimeField(null=True, blank=True)

    install = models.TextField(null=True, blank=True)
    post_work = models.TextField(null=True, blank=True)
    post_work_checked_by = models.ForeignKey(
        InvitedUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='post_work_checked_by'
    )
    post_work_check_on = models.DateTimeField(null=True, blank=True)
    day_install_began = models.DateTimeField(null=True, blank=True)
    day_install_complete = models.DateTimeField(null=True, blank=True)
    product_arrived_at_floor= models.TextField(null=True, blank=True)
    product_arrived_at_floor_checked_by = models.ForeignKey(
        InvitedUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='product_arrived_checked_by'
    )
    product_arrived_at_floor_check_on = models.DateTimeField(null=True, blank=True)

    retouching= models.TextField(null=True, blank=True)
    retouching_checked_by = models.ForeignKey(
        InvitedUser, null=True, blank=True, on_delete=models.SET_NULL, related_name='retouching_checked_by'
    )
    retouching_check_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'install'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room {self.room} - Installation Status"


class Inventory(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    item = models.TextField(null=True, blank=True)
    client_id = models.TextField(null=True, blank=True)
    qty_ordered = models.IntegerField(null=True, blank=True)
    qty_received = models.IntegerField(null=True, blank=True)
    quantity_installed = models.IntegerField(null=True, blank=True)
    quantity_available = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'inventory'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Item: {self.item} - Available: {self.quantity_available}"
    
class RoomModel(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room_model = models.TextField(null=True, blank=True)
    total = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'room_model'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room Model: {self.room_model} - Total: {self.total}"


class RoomData(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room = models.IntegerField(null=True, blank=True)
    floor = models.IntegerField(null=True, blank=True)
    king = models.TextField(null=True, blank=True)
    double = models.TextField(null=True, blank=True)
    exec_king = models.TextField(null=True, blank=True)
    bath_screen = models.TextField(null=True, blank=True)
    room_model = models.TextField(null=True, blank=True)
    room_model_id = models.ForeignKey(RoomModel, on_delete=models.SET_NULL, null=True, blank=True,db_column='room_model_id')
    left_desk = models.TextField(null=True, blank=True)
    right_desk = models.TextField(null=True, blank=True)
    to_be_renovated = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)  # Fixed column name typo from "descripton"

    class Meta:
        db_table = 'room_data'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room {self.room} - Floor {self.floor}"
    
    def save(self, *args, **kwargs):
        # Store the previous room_model_id before save
        old_room_model_id = None
        if self.pk:
            old = RoomData.objects.filter(pk=self.pk).first()
            if old:
                old_room_model_id = old.room_model_id_id

        super().save(*args, **kwargs)

        # Update totals for both old and new room_model_ids
        if old_room_model_id and old_room_model_id != self.room_model_id_id:
            RoomModel.objects.filter(id=old_room_model_id).update(
                total=RoomData.objects.filter(room_model_id=old_room_model_id).count()
            )

        if self.room_model_id_id:
            RoomModel.objects.filter(id=self.room_model_id_id).update(
                total=RoomData.objects.filter(room_model_id=self.room_model_id_id).count()
            )

    def delete(self, *args, **kwargs):
        room_model_id = self.room_model_id_id
        super().delete(*args, **kwargs)
        if room_model_id:
            RoomModel.objects.filter(id=room_model_id).update(
                total=RoomData.objects.filter(room_model_id=room_model_id).count()
            )

class Schedule(models.Model):
    id = models.AutoField(primary_key=True)
    phase = models.IntegerField(null=True, blank=True)
    floor = models.IntegerField(null=True, blank=True)
    production_starts = models.DateField(null=True, blank=True)
    production_ends = models.DateField(null=True, blank=True)
    shipping_depature = models.DateField(null=True, blank=True)
    shipping_arrival = models.DateField(null=True, blank=True)
    custom_clearing_starts = models.DateField(null=True, blank=True)
    custom_clearing_ends = models.DateField(null=True, blank=True)
    arrive_on_site = models.DateField(null=True, blank=True)
    pre_work_starts = models.DateField(null=True, blank=True)
    pre_work_ends = models.DateField(null=True, blank=True)
    install_starts = models.DateField(null=True, blank=True)
    install_ends = models.DateField(null=True, blank=True)  # Keep as DateField
    
    post_work_starts = models.DateField(null=True, blank=True)  # Changed to DateField
    post_work_ends = models.DateField(null=True, blank=True)  # Changed to DateField
    floor_completed = models.DateField(null=True, blank=True)  # Changed to DateField
    floor_closes = models.DateField(null=True, blank=True)  # Changed to DateField
    floor_opens = models.DateField(null=True, blank=True)  # Changed to DateField


    class Meta:
        db_table = 'schedule'  # Ensures it maps to the existing table

    def __str__(self):
        return f"Schedule - Phase: {self.phase}, Floor: {self.floor}"

class ProductData(models.Model):
    id = models.AutoField(primary_key=True)
    item = models.TextField(null=True, blank=True)
    client_id = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    client_selected = models.TextField(null=True, blank=True)
    supplier = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'product_data'  # Ensures it maps to the correct table

    def __str__(self):
        return f"ProductData - Item: {self.item}, Client: {self.client_id}"

class Prompt(models.Model):
    id = models.AutoField(primary_key=True)
    prompt_number = models.IntegerField(unique=True)
    prompt_name = models.CharField(max_length=255, null=True)
    description = models.TextField()

    def __str__(self):
        return f"Prompt {self.prompt_number}: {self.description[:50]}"  # Show first 50 chars

class ChatSession(models.Model):
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.id}"  # Fixed: Using self.id instead of self.session_id

class ChatHistory(models.Model):
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="chat_history", to_field="id")
    message = models.TextField()
    role = models.CharField(max_length=50)

    def __str__(self):
        return f"Message {self.id} in Session {self.session.id}"

class Shipping(models.Model):
    client_id = models.CharField(max_length=255)
    item = models.CharField(max_length=255)
    ship_date = models.DateField()
    ship_qty = models.PositiveIntegerField()
    supplier = models.CharField(max_length=255)
    bol = models.CharField("Bill of Lading", max_length=100, unique=True)
    checked_by = models.ForeignKey(InvitedUser, on_delete=models.SET_NULL, null=True, blank=True,db_column='checked_by')
    expected_arrival_date = models.DateTimeField(default=None,null=True, blank=True)

    def __str__(self):
        return f"Shipment {self.bol} - {self.item} to Client {self.client_id}"
    class Meta:
        db_table = "shipping"


class PullInventory(models.Model):
    client_id =  models.CharField(max_length=255)
    item = models.CharField(max_length=255)
    available_qty = models.PositiveIntegerField(default=0)
    pulled_date = models.DateField(null=True, blank=True)
    qty_pulled = models.PositiveIntegerField(default=0)
    pulled_by = models.ForeignKey(InvitedUser, on_delete=models.SET_NULL, null=True, blank=True,db_column='checked_by')
    floor = models.CharField(max_length=100, blank=True)
    qty_available_after_pull = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Pull - {self.item} for Client {self.client_id}"
    class Meta:
        db_table = "pull_inventory"

class InstallDetail(models.Model):
    install_id = models.AutoField(primary_key=True)
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE, null=True, blank=True, related_name='install_details')
    product_id=models.ForeignKey(ProductData, on_delete=models.SET_NULL, null=True, blank=True,db_column='product_id')
    room_model_id=models.ForeignKey(RoomModel, on_delete=models.SET_NULL, null=True, blank=True,db_column='room_model_id')
    room_id = models.ForeignKey(RoomData, on_delete=models.SET_NULL, null=True, blank=True,db_column='room_id')
    product_name = models.CharField(max_length=255)
    installed_by = models.ForeignKey(InvitedUser, on_delete=models.SET_NULL, null=True, blank=True,db_column='installed_by')
    installed_on = models.DateTimeField(default=None,null=True, blank=True)
    status=models.TextField(default='NO')

    def __str__(self):
        return f"Install {self.install_id} - {self.product_name} in Room {self.room_id}"
    class Meta:
        db_table = "install_detail"


class ProductRoomModel(models.Model):
    id=models.AutoField(primary_key=True)
    product_id=models.ForeignKey(ProductData, on_delete=models.SET_NULL, null=True, blank=True,db_column='product_id')
    room_model_id=models.ForeignKey(RoomModel, on_delete=models.SET_NULL, null=True, blank=True,db_column='room_model_id')
    quantity=models.IntegerField(null=True)

    class Meta:
        db_table = "product_room_model"

class InventoryReceived(models.Model):
    client_id = models.CharField(max_length=255)
    item = models.CharField(max_length=255)
    received_date = models.DateTimeField()
    received_qty = models.PositiveIntegerField()
    damaged_qty = models.PositiveIntegerField()
    checked_by = models.ForeignKey(InvitedUser, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Received {self.received_qty} of {self.item} for {self.client_id}"

    class Meta:
        db_table = "inventory_received"

class IssueStatus(models.TextChoices):
    OPEN = 'OPEN', _('Open')
    CLOSE = 'CLOSE', _('Close')
    PENDING = 'PENDING', _('Pending')
    WORKING = 'WORKING', _('Working')

class IssueType(models.TextChoices):
    ROOM = 'ROOM', _('Room')
    FLOOR = 'FLOOR', _('Floor')
    INVENTORY = 'INVENTORY', _('Inventory') # Added INVENTORY based on description

class Issue(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'InvitedUser',
        on_delete=models.PROTECT,
        related_name='created_issues'
    )
    status = models.CharField(
        max_length=10,
        choices=IssueStatus.choices,
        default=IssueStatus.OPEN
    )
    type = models.CharField(
        max_length=10,
        choices=IssueType.choices
        # Default type might be better set in the view based on context
    )
    is_for_hotel_admin = models.BooleanField(default=False)
    assignee = models.ForeignKey(
        'InvitedUser',
        on_delete=models.SET_NULL,
        related_name='assigned_issues',
        blank=True,
        null=True
    )
    observers = models.ManyToManyField(
        'InvitedUser',
        related_name='observed_issues',
        blank=True
    )

    def __str__(self):
        return f"{self.id}: {self.title} ({self.status})"

class Comment(models.Model):
    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE, # Delete comments if the issue is deleted
        related_name='comments'
    )
    user = models.ForeignKey(
        'InvitedUser',
        on_delete=models.PROTECT,
        related_name='issue_comments'
    )
    text_content = models.TextField(blank=True, null=True)
    # Using JSONField for flexibility. Requires PostgreSQL or Django >= 3.1 with other DBs
    # Consider alternatives like a separate Media model if JSONField is not suitable
    media = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Comment by {self.user} on Issue {self.issue.id} at {self.created_at}"

# Potential next steps:
# - Add validation for media field (max images, video size) - likely in forms/serializers
# - Create a signal to automatically add creator to observers on Issue save

"""
from hotel_bot_app.models import Issue, IssueStatus, IssueType, InvitedUser
from django.utils import timezone
inv = InvitedUser.objects.filter(id=7).first()
issue2 = Issue.objects.create(

    title="Broken Tile on 3rd Floor Hallway",

    description="A tile in the hallway on the 3rd floor is cracked and loose. Potential tripping hazard.",

    created_by=inv,

    status=IssueStatus.WORKING,

    type=IssueType.FLOOR,

    assignee=None,

    is_for_hotel_admin=True,

    created_at=timezone.now() - timezone.timedelta(days=1) # Example of setting a past creation date

)
"""
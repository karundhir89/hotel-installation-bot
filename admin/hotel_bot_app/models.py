from django.db import models

from django.db import models
from django.contrib.postgres.fields import ArrayField

class Installation(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room = models.TextField(null=True, blank=True)
    product_available = models.TextField(null=True, blank=True)
    prework = models.TextField(null=True, blank=True)
    install = models.TextField(null=True, blank=True)
    post_work = models.TextField(null=True, blank=True)
    day_install_began = models.TextField(null=True, blank=True)
    day_instal_complete = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'install'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room {self.room} - Installation Status"


class Inventory(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    item = models.TextField(null=True, blank=True)
    client_id = models.TextField(null=True, blank=True)
    qty_ordered = models.TextField(null=True, blank=True)
    qty_received = models.TextField(null=True, blank=True)
    quantity_installed = models.TextField(null=True, blank=True)
    quantity_available = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'inventory'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Item: {self.item} - Available: {self.quantity_available}"



class RoomData(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room = models.TextField(null=True, blank=True)
    floor = models.TextField(null=True, blank=True)
    king = models.TextField(null=True, blank=True)
    double = models.TextField(null=True, blank=True)
    exec_king = models.TextField(null=True, blank=True)
    bath_screen = models.TextField(null=True, blank=True)
    room_model = models.TextField(null=True, blank=True)
    left_desk = models.TextField(null=True, blank=True)
    right_desk = models.TextField(null=True, blank=True)
    to_be_renovated = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)  # Fixed column name typo from "descripton"

    class Meta:
        db_table = 'room_data'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room {self.room} - Floor {self.floor}"
    
class RoomModel(models.Model):
    id = models.AutoField(primary_key=True)  # Serial (Auto-increment)
    room_model = models.TextField(null=True, blank=True)
    total = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'room_model'  # Ensure this matches the actual table name in PostgreSQL

    def __str__(self):
        return f"Room Model: {self.room_model} - Total: {self.total}"
    

class Schedule(models.Model):
    id = models.AutoField(primary_key=True)
    phase = models.TextField(null=True, blank=True)
    floor = models.TextField(null=True, blank=True)
    production_starts = models.DateTimeField(null=True, blank=True)
    production_ends = models.DateTimeField(null=True, blank=True)
    shipping_depature = models.DateTimeField(null=True, blank=True)
    shipping_arrival = models.DateTimeField(null=True, blank=True)
    custom_clearing_starts = models.DateTimeField(null=True, blank=True)
    custom_clearing_ends = models.DateTimeField(null=True, blank=True)
    arrive_on_site = models.DateTimeField(null=True, blank=True)
    pre_work_starts = models.DateTimeField(null=True, blank=True)
    pre_work_ends = models.DateTimeField(null=True, blank=True)
    install_starts = models.DateTimeField(null=True, blank=True)
    install_ends = models.DateTimeField(null=True, blank=True)  # Keep as DateTimeField
    
    post_work_starts = models.DateTimeField(null=True, blank=True)  # Changed to DateTimeField
    post_work_ends = models.DateTimeField(null=True, blank=True)  # Changed to DateTimeField
    floor_completed = models.DateTimeField(null=True, blank=True)  # Changed to DateTimeField
    floor_closes = models.DateTimeField(null=True, blank=True)  # Changed to DateTimeField
    floor_opens = models.DateTimeField(null=True, blank=True)  # Changed to DateTimeField


    class Meta:
        db_table = 'schedule'  # Ensures it maps to the existing table

    def __str__(self):
        return f"Schedule - Phase: {self.phase}, Floor: {self.floor}"

from django.db import models

class ProductData(models.Model):
    id = models.AutoField(primary_key=True)
    item = models.TextField(null=True, blank=True)
    client_id = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    qty_ordered = models.TextField(null=True, blank=True)
    price = models.TextField(null=True, blank=True)
    a = models.TextField(null=True, blank=True)
    a_col = models.TextField(null=True, blank=True)
    a_lo = models.TextField(null=True, blank=True)
    a_lo_dr = models.TextField(null=True, blank=True)
    b = models.TextField(null=True, blank=True)
    c_pn = models.TextField(null=True, blank=True)
    c = models.TextField(null=True, blank=True)
    curva_24 = models.TextField(null=True, blank=True)
    curva = models.TextField(null=True, blank=True)
    curva_dis = models.TextField(null=True, blank=True)
    d = models.TextField(null=True, blank=True)
    dlx = models.TextField(null=True, blank=True)
    presidential_suite = models.TextField(null=True, blank=True)
    st_c = models.TextField(null=True, blank=True)
    suite_a = models.TextField(null=True, blank=True)
    suite_b = models.TextField(null=True, blank=True)
    suite_c = models.TextField(null=True, blank=True)
    suite_mini = models.TextField(null=True, blank=True)
    curva_35 = models.TextField(null=True, blank=True)
    client_selected = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'product_data'  # Ensures it maps to the correct table

    def __str__(self):
        return f"ProductData - Item: {self.item}, Client: {self.client_id}"

class Prompt(models.Model):
    id = models.AutoField(primary_key=True)
    prompt_number = models.IntegerField(unique=True)
    description = models.TextField()

    def __str__(self):
        return f"Prompt {self.prompt_number}: {self.description[:50]}"  # Show first 50 chars
from django.db import models

from django.db import models

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

class InvitedUser(models.Model):
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
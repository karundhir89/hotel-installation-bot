from django.contrib import admin
from .models import Issue, Comment, InvitedUser, Inventory, InventoryReceived # Assuming other models are already imported

# Basic registration first, can customize later
admin.site.register(Issue)
admin.site.register(Comment)

# Keep existing registrations
admin.site.register(InvitedUser)
admin.site.register(Inventory)
admin.site.register(InventoryReceived)

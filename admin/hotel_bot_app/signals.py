from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import Shipping, Inventory, WarehouseRequest, InstallDetail
import logging

logger = logging.getLogger(__name__)

@receiver([post_save, post_delete], sender=Shipping)
def update_inventory_shipped_quantity(sender, instance, **kwargs):
    """
    Update the quantity_shipped in Inventory table whenever a Shipping record is added, updated, or deleted
    """
    try:
        print(f"Signal triggered for Shipping record: client_id={instance.client_id}, ship_qty={instance.ship_qty}")
        
        # Get all shipping records for this client_id (case-insensitive)
        shipping_records = Shipping.objects.filter(client_id__iexact=instance.client_id)
        total_shipped = shipping_records.aggregate(total=Sum('ship_qty'))['total'] or 0
        
        print(f"Found {shipping_records.count()} shipping records for client_id={instance.client_id} (case-insensitive)")
        print(f"Total shipped quantity: {total_shipped}")
        
        # First try to find existing inventory record case-insensitively
        try:
            inventory = Inventory.objects.get(client_id__iexact=instance.client_id)
            print(f"Found existing inventory record for client_id={instance.client_id}")
            inventory.quantity_shipped = total_shipped
            inventory.save()
        except Inventory.DoesNotExist:
            # If no record exists, create a new one
            print(f"Creating new inventory record for client_id={instance.client_id}")
            inventory = Inventory.objects.create(
                client_id=instance.client_id,
                item=instance.client_id,
                quantity_shipped=total_shipped
            )

        print(f"Successfully updated quantity_shipped to {total_shipped} for client_id={instance.client_id}")
            
    except Exception as e:
        print(f"Error updating inventory shipped quantity: {str(e)}")
        logger.error(f"Error updating inventory shipped quantity: {str(e)}", exc_info=True)

@receiver([post_save, post_delete], sender=WarehouseRequest)
def update_inventory_floor_quantity(sender, instance, **kwargs):
    """
    Update the floor_quantity in Inventory table whenever a WarehouseRequest record is added, updated, or deleted
    """
    try:
        print(f"Signal triggered for WarehouseRequest record: client_item={instance.client_item}")

        # Get all warehouse request records for this client_item (case-insensitive)
        warehouse_records = WarehouseRequest.objects.filter(client_item__iexact=instance.client_item)
        total_sent = warehouse_records.aggregate(total=Sum('quantity_sent'))['total'] or 0

        print(f"Found {warehouse_records.count()} warehouse request records for client_item={instance.client_item}")
        print(f"Total quantity sent: {total_sent}")

        # First try to find existing inventory record case-insensitively
        try:
            inventory = Inventory.objects.get(client_id__iexact=instance.client_item)
            print(f"Found existing inventory record for client_id={instance.client_item}")
            inventory.floor_quantity = total_sent
            inventory.save()
        except Inventory.DoesNotExist:
            # If no record exists, create a new one
            print(f"Creating new inventory record for client_id={instance.client_item}")
            inventory = Inventory.objects.create(
                client_id=instance.client_item,
                item=instance.client_item,
                floor_quantity=total_sent
            )

        print(f"Successfully updated floor_quantity to {total_sent} for client_id={instance.client_item}")

    except Exception as e:
        print(f"Error updating inventory floor quantity: {str(e)}")
        logger.error(f"Error updating inventory floor quantity: {str(e)}", exc_info=True)

# All other signals disabled to avoid infinite recursion and conflicts with manual updates 


# --- InstallDetail signals: keep Inventory.hotel_warehouse_quantity and quantity_installed in sync ---
@receiver(pre_save, sender=InstallDetail)
def install_detail_pre_save(sender, instance, **kwargs):
    """Store previous status on instance so post_save can detect a change."""
    try:
        if instance.pk:
            old = InstallDetail.objects.get(pk=instance.pk)
            instance._old_status = old.status
        else:
            instance._old_status = None
    except InstallDetail.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=InstallDetail)
def install_detail_post_save(sender, instance, created, **kwargs):
    """When an install detail is created/updated, adjust Inventory counts.

    Behavior:
    - If status changed from not-YES to YES: decrement hotel_warehouse_quantity by 1 and increment quantity_installed.
    - If status changed from YES to not-YES: increment hotel_warehouse_quantity by 1 and decrement quantity_installed.
    - If created with status YES: treat as installed.
    We also recalculate quantity_installed deterministically from DB to avoid drift.
    """
    try:
        prod = instance.product_id
        if not prod or not prod.client_id:
            return
        client = prod.client_id
        inv = Inventory.objects.filter(client_id__iexact=client).first()
        if not inv:
            return

        # Recompute all relevant aggregates deterministically to avoid drift
        from hotel_bot_app.models import HotelWarehouse, WarehouseRequest
        from django.db.models import Sum

        total_received = HotelWarehouse.objects.filter(client_item__iexact=client).aggregate(s=Sum('quantity_received'))['s'] or 0
        total_damaged = HotelWarehouse.objects.filter(client_item__iexact=client).aggregate(s=Sum('damaged_qty'))['s'] or 0
        installed_count = InstallDetail.objects.filter(product_id__client_id__iexact=client, status__iexact='YES').count()
        floor_sent = WarehouseRequest.objects.filter(client_item__iexact=client).aggregate(s=Sum('quantity_sent'))['s'] or 0

        # Hotel warehouse should reflect received minus damaged, minus what has been sent to floor and minus installed
        # (this formula may be adjusted if your business rules differ)
        hotel_qty = total_received - total_damaged - floor_sent - installed_count
        if hotel_qty < 0:
            hotel_qty = 0

        inv.received_at_hotel_quantity = total_received
        inv.damaged_quantity_at_hotel = total_damaged
        inv.quantity_installed = installed_count
        inv.hotel_warehouse_quantity = hotel_qty
        inv.save(update_fields=['received_at_hotel_quantity', 'damaged_quantity_at_hotel', 'quantity_installed', 'hotel_warehouse_quantity'])
        logger.debug(f"Recomputed Inventory for {client}: received={total_received}, damaged={total_damaged}, floor_sent={floor_sent}, installed={installed_count}, hotel_warehouse={hotel_qty}")
    except Exception as e:
        logger.exception("Error updating Inventory from InstallDetail post_save: %s", e)


@receiver(post_delete, sender=InstallDetail)
def install_detail_post_delete(sender, instance, **kwargs):
    """If an installed install_detail is deleted, adjust inventory accordingly."""
    try:
        prod = instance.product_id
        if not prod or not prod.client_id:
            return
        client = prod.client_id
        inv = Inventory.objects.filter(client_id__iexact=client).first()
        if not inv:
            return

        # Recompute all aggregates as in post_save
        from hotel_bot_app.models import HotelWarehouse, WarehouseRequest
        from django.db.models import Sum

        total_received = HotelWarehouse.objects.filter(client_item__iexact=client).aggregate(s=Sum('quantity_received'))['s'] or 0
        total_damaged = HotelWarehouse.objects.filter(client_item__iexact=client).aggregate(s=Sum('damaged_qty'))['s'] or 0
        installed_count = InstallDetail.objects.filter(product_id__client_id__iexact=client, status__iexact='YES').count()
        floor_sent = WarehouseRequest.objects.filter(client_item__iexact=client).aggregate(s=Sum('quantity_sent'))['s'] or 0

        hotel_qty = total_received - total_damaged - floor_sent - installed_count
        if hotel_qty < 0:
            hotel_qty = 0

        inv.received_at_hotel_quantity = total_received
        inv.damaged_quantity_at_hotel = total_damaged
        inv.quantity_installed = installed_count
        inv.hotel_warehouse_quantity = hotel_qty
        inv.save(update_fields=['received_at_hotel_quantity', 'damaged_quantity_at_hotel', 'quantity_installed', 'hotel_warehouse_quantity'])
        logger.debug(f"Post-delete recomputed Inventory for {client}: received={total_received}, damaged={total_damaged}, floor_sent={floor_sent}, installed={installed_count}, hotel_warehouse={hotel_qty}")
    except Exception as e:
        logger.exception("Error updating Inventory from InstallDetail post_delete: %s", e)
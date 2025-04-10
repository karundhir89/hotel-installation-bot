# Generated by Django 4.1 on 2025-04-10 05:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hotel_bot_app', '0002_roomdata_room_model_id_alter_inventory_qty_ordered_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PullInventory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=255)),
                ('item', models.CharField(max_length=255)),
                ('available_qty', models.PositiveIntegerField(default=0)),
                ('is_pulled', models.BooleanField(default=False)),
                ('pulled_date', models.DateField(blank=True, null=True)),
                ('qty_pulled_for_install', models.PositiveIntegerField(default=0)),
                ('pulled_by', models.CharField(max_length=255)),
                ('floor', models.CharField(blank=True, max_length=100)),
                ('qty_pulled', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'db_table': 'pull_inventory',
            },
        ),
        migrations.CreateModel(
            name='Shipping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=255)),
                ('item', models.CharField(max_length=255)),
                ('ship_date', models.DateField()),
                ('ship_qty', models.PositiveIntegerField()),
                ('supplier', models.CharField(max_length=255)),
                ('supplier_date', models.DateField(blank=True, null=True)),
                ('bol', models.CharField(max_length=100, unique=True, verbose_name='Bill of Lading')),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('by', models.CharField(max_length=255, verbose_name='Handled By')),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'db_table': 'Shipping',
            },
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='a',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='a_col',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='a_lo',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='a_lo_dr',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='b',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='c',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='c_pn',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='curva',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='curva_24',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='curva_35',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='curva_dis',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='d',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='dlx',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='presidential_suite',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='qty_ordered',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='st_c',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='suite_a',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='suite_b',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='suite_c',
        ),
        migrations.RemoveField(
            model_name='productdata',
            name='suite_mini',
        ),
        migrations.AddField(
            model_name='installation',
            name='product_arrived_at_floor',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='installation',
            name='retouching',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='installation',
            name='day_instal_complete',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='installation',
            name='day_install_began',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='installation',
            name='room',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='inviteduser',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='productdata',
            name='price',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='roomdata',
            name='floor',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='roomdata',
            name='room',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='roommodel',
            name='total',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='floor',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='phase',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ProductRoomModel',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('quantity', models.IntegerField(null=True)),
                ('product_id', models.ForeignKey(blank=True, db_column='product_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.productdata')),
                ('room_model_id', models.ForeignKey(blank=True, db_column='room_model_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.roommodel')),
            ],
            options={
                'db_table': 'product_room_model',
            },
        ),
        migrations.CreateModel(
            name='InstallDetail',
            fields=[
                ('install_id', models.AutoField(primary_key=True, serialize=False)),
                ('product_name', models.CharField(max_length=255)),
                ('installed_on', models.DateField()),
                ('status', models.TextField(default='NO')),
                ('installed_by', models.ForeignKey(blank=True, db_column='installed_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.inviteduser')),
                ('product_id', models.ForeignKey(blank=True, db_column='product_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.productdata')),
                ('room_id', models.ForeignKey(blank=True, db_column='room_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.roomdata')),
                ('room_model_id', models.ForeignKey(blank=True, db_column='room_model_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hotel_bot_app.roommodel')),
            ],
            options={
                'db_table': 'install_detail',
            },
        ),
    ]

from django.shortcuts import render,HttpResponseRedirect, redirect, get_object_or_404
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from functools import wraps
from .models import *

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse # Though reverse might not be strictly needed if using namespaced redirects
import uuid
from django.core.files.storage import default_storage
import json # For AJAX error responses if you re-add them later

from hotel_bot_app.models import Issue, Comment, InvitedUser 
from hotel_bot_app.forms import IssueUpdateForm, CommentForm, IssueForm

import logging
logger = logging.getLogger(__name__)

# Define a check for staff users (Django's concept of admin users)
def is_staff_user(user):
	return user.is_authenticated and user.is_staff # or user.is_superuser
from hotel_bot_app.models import *
from django.db.models import Count, Q # Q object can be useful for complex queries if needed
from django.db import connection # Added for raw SQL


# Create your views here.
@login_required
def my_view(request):
	try:
		username = request.POST['username']
		password = request.POST['password']
		user = authenticate(username=username, password=password)
		print("user>>>>>>",user)
		if user is not None:
			if user.is_active:
				login(request, user)
				return HttpResponseRedirect("/user_management")
	except Exception as e:
		print("error in my_view :::::::::::",e)
	return HttpResponseRedirect("/admin/login")

@login_required
def change_password(request):
	try:
		if request.method == 'POST':
			form = PasswordChangeForm(request.user, request.POST)
			if form.is_valid():
				print('valid change password form')
				user = form.save()
				messages.success(request,"Password Changed Successfully")
				return HttpResponseRedirect('change-password')
			else:
				print ('in valid change password form')
		else:
			form = PasswordChangeForm(request.user)

		return render(request, 'registration/change_password.html', {
			'form': form,'page_name':'Change Password'
			})

	except Exception as e:
		print("Error in change_password :::::::::::::::::::: ",e)
		messages.error(request,"Error on server end, Please contact developer.")

def show_login(request):
	try:
		print("user id :::: ",request.user)
		if request.user.id is not None:
				return HttpResponseRedirect('user_management')
		else:
			return HttpResponseRedirect('user_login')
	except Exception as e:
		print('error in  show_login',str(e))
	return HttpResponseRedirect('dashboard')

@login_required	
def logout_view(request):
	try:
		logout(request)
		return HttpResponseRedirect("/admin/login")
	except Exception as e:
		print("error in logout :::::::::::",e)

@login_required
@user_passes_test(is_staff_user) # Protects for staff users
def admin_issue_list(request):
	issue_list_all = Issue.objects.all().order_by('-created_at').select_related('created_by', 'assignee')
	paginator = Paginator(issue_list_all, 25) # Show 25 issues per page
	page_number = request.GET.get('page')
	try:
		issues_page = paginator.page(page_number)
	except PageNotAnInteger:
		# If page is not an integer, deliver first page.
		issues_page = paginator.page(1)
	except EmptyPage:
		# If page is out of range (e.g. 9999), deliver last page of results.
		issues_page = paginator.page(paginator.num_pages)
	
	context = {
		'issues_page': issues_page,
	}
	return render(request, 'admin_dashboard/issues/admin_issue_list.html', context)

@login_required
@user_passes_test(is_staff_user)
def admin_issue_edit(request, issue_id):
	issue = get_object_or_404(Issue, pk=issue_id)
	available_users = InvitedUser.objects.all()
	
	if request.method == 'POST':
		form = IssueUpdateForm(request.POST, instance=issue)
		if form.is_valid():
			# Get the observers from the form data
			observer_ids = request.POST.getlist('observers')
			# Clear existing observers
			issue.observers.clear()
			# Add new observers
			for observer_id in observer_ids:
				try:
					observer = InvitedUser.objects.get(id=observer_id)
					issue.observers.add(observer)
				except InvitedUser.DoesNotExist:
					continue
			
			form.save()
			messages.success(request, f"Issue #{issue.id} updated successfully.")
			# return redirect('admin_dashboard:admin_issue_list')
		else:
			messages.error(request, "Please correct the errors below.")
	else:
		form = IssueUpdateForm(instance=issue)
	
	context = {
		'form': form,
		'issue': issue,
		'available_users': available_users,
		'observers': issue.observers.all(),  # Pass the current observers to the template
	}
	return render(request, 'admin_dashboard/issues/admin_issue_form.html', context)


@login_required
@user_passes_test(is_staff_user)
def admin_issue_detail(request, issue_id):
    issue = get_object_or_404(Issue, id=issue_id)
    comments = issue.comments.all().select_related('content_type')
    
    # Force evaluation of GenericForeignKey
    for comment in comments:
        _ = comment.commenter

    comment_form = CommentForm()

    current_user_commenter = request.user  # Assuming User model is used as commenter

    comment_data = []
    for comment in comments:
        commenter = comment.commenter
        comment_data.append({
            "comment_id": comment.id,
            "text_content": comment.text_content,
            "media": comment.media,
            "commenter_id": getattr(commenter, "id", None),
            "commenter_name": str(commenter),
            "is_by_current_user": commenter == current_user_commenter
        })

    context = {
        'issue': issue,
        'comments': comments,
        'comment_form': comment_form,
        'user': request.user,
        'can_comment': True,
        'comment_data': comment_data,  # <-- Added this
    }
    return render(request, 'admin_dashboard/issues/admin_issue_detail.html', context)

@login_required
@user_passes_test(is_staff_user)
def admin_comment_create(request, issue_id):
	issue = get_object_or_404(Issue, id=issue_id)
	admin_user = request.user 

	if request.method == 'POST':
		form = CommentForm(request.POST, request.FILES)
		if form.is_valid():
			comment = form.save(commit=False)
			comment.commenter = admin_user 
			comment.issue = issue
			
			media_info = []
			images = form.cleaned_data.get('images', []) 
			video = form.cleaned_data.get('video')

			for img in images: 
				if img.size > 4 * 1024 * 1024: # 4MB
					messages.error(request, f"Image '{img.name}' exceeds 4MB limit.")
					continue
				file_name = default_storage.save(f"issues/comments/admin/{issue.id}/{uuid.uuid4()}_{img.name}", img)
				media_info.append({"type": "image", "url": default_storage.url(file_name), "name": img.name, "size": img.size})

			if video:
				if video.size > 100 * 1024 * 1024: # 100MB
					messages.error(request, f"Video '{video.name}' exceeds 100MB limit.")
				else:
					file_name = default_storage.save(f"issues/comments/admin/{issue.id}/{uuid.uuid4()}_{video.name}", video)
					media_info.append({"type": "video", "url": default_storage.url(file_name), "name": video.name, "size": video.size})
			
			comment.media = media_info
			comment.save()
			messages.success(request, "Admin comment added successfully.")
			return redirect('admin_dashboard:admin_issue_detail', issue_id=issue.id) 
		else:
			messages.error(request, "Error submitting admin comment.")
			comments_qs = issue.comments.all().select_related('content_type')
			for c_item in comments_qs:
				_ = c_item.commenter
			context = {
				'issue': issue,
				'comments': comments_qs,
				'comment_form': form, 
				'user': request.user
			}
			return render(request, 'admin_dashboard/issues/admin_issue_detail.html', context)
	else: 
		return redirect('admin_dashboard:admin_issue_detail', issue_id=issue.id)

def _dictfetchall(cursor):
    """Return all rows from a cursor as a list of dictionaries."""
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

def _prepare_floor_progress_data():
    """
    Prepares the data for the floor renovation progress table using raw SQL.
    Also prepares a summary of floor renovation statuses.
    Returns a tuple: (floor_progress_list, total_project_rooms, total_project_fully_completed_rooms, floor_status_summary)
    """
    floor_progress_list = []
    total_project_rooms_accumulator = 0
    total_project_fully_completed_rooms_accumulator = 0

    renovated_floor_numbers = []
    closed_floor_numbers = [] # Floors in progress
    pending_floor_numbers = []

    sql_query = """
        SELECT
            rd.floor AS floor_number,
            COUNT(rd.id) AS total_rooms_on_floor,
            COALESCE(SUM(CASE WHEN i.prework_check_on IS NOT NULL THEN 1 ELSE 0 END), 0) AS prework_completed_count,
            COALESCE(SUM(CASE WHEN i.day_install_complete IS NOT NULL THEN 1 ELSE 0 END), 0) AS install_completed_count,
            COALESCE(SUM(CASE WHEN i.post_work_check_on IS NOT NULL THEN 1 ELSE 0 END), 0) AS postwork_completed_count,
            COALESCE(SUM(CASE 
                WHEN i.prework_check_on IS NOT NULL AND 
                     i.day_install_complete IS NOT NULL AND 
                     i.post_work_check_on IS NOT NULL 
                THEN 1 ELSE 0 
            END), 0) AS fully_completed_rooms_on_floor
        FROM
            room_data rd
        LEFT JOIN
            install i ON rd.room = i.room
        WHERE
            rd.floor IS NOT NULL
        GROUP BY
            rd.floor
        ORDER BY
            rd.floor;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql_query)
        results = _dictfetchall(cursor)

    for row in results:
        current_floor = row['floor_number']
        total_rooms_on_floor = int(row['total_rooms_on_floor'])
        prework_completed = int(row['prework_completed_count'])
        install_completed = int(row['install_completed_count'])
        postwork_completed = int(row['postwork_completed_count'])
        fully_completed_on_floor = int(row['fully_completed_rooms_on_floor'])

        total_project_rooms_accumulator += total_rooms_on_floor
        total_project_fully_completed_rooms_accumulator += fully_completed_on_floor

        percentage_completed_str = "0%"
        prework_status = "Pending"
        install_status_str = "Pending"
        postwork_status = "Pending"

        if total_rooms_on_floor > 0:
            percentage_completed_val = (fully_completed_on_floor / total_rooms_on_floor * 100)
            percentage_completed_str = f"{percentage_completed_val:.0f}%"

            prework_status = "Completed" if prework_completed == total_rooms_on_floor else "Pending"
            
            if install_completed == total_rooms_on_floor:
                install_status_str = "Completed"
            elif install_completed > 0:
                install_percentage_val = (install_completed / total_rooms_on_floor * 100)
                install_status_str = f"{install_percentage_val:.0f}%"
            # else install_status_str remains "Pending"

            postwork_status = "Completed" if postwork_completed == total_rooms_on_floor else "Pending"
        
        floor_progress_list.append({
            'floor_number': current_floor,
            'percentage_completed': percentage_completed_str,
            'prework_status': prework_status,
            'install_status': install_status_str,
            'postwork_status': postwork_status,
        })

        # --- Categorize floors for summary --- 
        if total_rooms_on_floor > 0: # Ensure floor has rooms to be considered
            if fully_completed_on_floor == total_rooms_on_floor:
                renovated_floor_numbers.append(current_floor)
            elif install_completed > 0: # Some installation started, but not all rooms fully completed
                closed_floor_numbers.append(current_floor)
            else: # No installation started
                pending_floor_numbers.append(current_floor)
        else: # Floors with no rooms in room_data but potentially in schedule (not covered by this SQL)
            pending_floor_numbers.append(current_floor) # Or handle as per broader project definition if available
    
    floor_status_summary = {
        'renovated': {
            'count': len(renovated_floor_numbers),
            'numbers': sorted(list(set(renovated_floor_numbers))) # Ensure unique and sorted
        },
        'closed': {
            'count': len(closed_floor_numbers),
            'numbers': sorted(list(set(closed_floor_numbers)))
        },
        'pending': {
            'count': len(pending_floor_numbers),
            'numbers': sorted(list(set(pending_floor_numbers)))
        }
    }
    
    return floor_progress_list, total_project_rooms_accumulator, total_project_fully_completed_rooms_accumulator, floor_status_summary

def _prepare_pie_chart_data(total_project_rooms, total_project_fully_completed_rooms):
	"""
	Prepares the data for the overall project completion pie chart.
	"""
	overall_completion_percentage = (total_project_fully_completed_rooms / total_project_rooms * 100) if total_project_rooms > 0 else 0
	pending_completion_percentage = 100 - overall_completion_percentage

	return {
		'completed': round(overall_completion_percentage, 1),
		'pending': round(pending_completion_percentage, 1),
	}

EXPECTED_ROOM_TIMES = {
    'pre_work': 7,
    'install': 7,
    'post_work': 4,
    'total': 18
}

EXPECTED_FLOOR_TIMES = {
    'pre_work': 14,
    'install': 14,
    'post_work': 7,
    'total': 35
}

def _prepare_efficiency_data():
    """
    Calculates average phase completion times for rooms and floors using raw SQL.
    Returns a dictionary with average times and expected times for both.
    """
    # Initialize results
    avg_room_times = {'pre_work': 0, 'install': 0, 'post_work': 0, 'total': 0}
    avg_floor_times = {'pre_work': 0, 'install': 0, 'post_work': 0, 'total': 0}

    # 1. Calculate Room-Level Average Durations
    room_sql_query = """
        SELECT
            AVG(CASE
                WHEN i.prework_check_on IS NOT NULL AND i.day_install_began IS NOT NULL AND i.prework_check_on >= i.day_install_began
                THEN EXTRACT(EPOCH FROM (i.prework_check_on - i.day_install_began)) / 86400.0
                ELSE NULL
            END) AS avg_room_pre_work_duration,
            AVG(CASE
                WHEN i.day_install_complete IS NOT NULL AND i.prework_check_on IS NOT NULL AND i.day_install_complete >= i.prework_check_on
                THEN EXTRACT(EPOCH FROM (i.day_install_complete - i.prework_check_on)) / 86400.0
                ELSE NULL
            END) AS avg_room_install_duration,
            AVG(CASE
                WHEN i.post_work_check_on IS NOT NULL AND i.day_install_complete IS NOT NULL AND i.post_work_check_on >= i.day_install_complete
                THEN EXTRACT(EPOCH FROM (i.post_work_check_on - i.day_install_complete)) / 86400.0
                ELSE NULL
            END) AS avg_room_post_work_duration
        FROM
            install i;
    """
    with connection.cursor() as cursor:
        cursor.execute(room_sql_query)
        result = cursor.fetchone()
        if result:
            avg_room_times['pre_work'] = round(result[0], 0) if result[0] is not None else 0
            avg_room_times['install'] = round(result[1], 0) if result[1] is not None else 0
            avg_room_times['post_work'] = round(result[2], 0) if result[2] is not None else 0
            avg_room_times['total'] = sum(filter(None, [avg_room_times['pre_work'], avg_room_times['install'], avg_room_times['post_work']]))
            avg_room_times['total'] = round(avg_room_times['total'],0)

    # 2. Calculate Floor-Level Average Durations
    floor_sql_query = """
        WITH FloorPhaseActuals AS (
            SELECT
                rd.floor,
                MIN(i.day_install_began) as actual_floor_pre_work_start,
                MAX(i.prework_check_on) as actual_floor_pre_work_end,
                MAX(i.day_install_complete) as actual_floor_install_end,
                MAX(i.post_work_check_on) as actual_floor_post_work_end
            FROM
                install i
            JOIN
                room_data rd ON i.room = rd.room
            WHERE 
                rd.floor IS NOT NULL
            GROUP BY
                rd.floor
        ),
        FloorPhaseDurations AS (
            SELECT
                floor,
                CASE 
                    WHEN actual_floor_pre_work_end IS NOT NULL AND actual_floor_pre_work_start IS NOT NULL AND actual_floor_pre_work_end >= actual_floor_pre_work_start
                    THEN EXTRACT(EPOCH FROM (actual_floor_pre_work_end - actual_floor_pre_work_start)) / 86400.0
                    ELSE NULL 
                END AS floor_pre_work_duration,
                CASE
                    WHEN actual_floor_install_end IS NOT NULL AND actual_floor_pre_work_end IS NOT NULL AND actual_floor_install_end >= actual_floor_pre_work_end
                    THEN EXTRACT(EPOCH FROM (actual_floor_install_end - actual_floor_pre_work_end)) / 86400.0
                    ELSE NULL
                END AS floor_install_duration,
                CASE
                    WHEN actual_floor_post_work_end IS NOT NULL AND actual_floor_install_end IS NOT NULL AND actual_floor_post_work_end >= actual_floor_install_end
                    THEN EXTRACT(EPOCH FROM (actual_floor_post_work_end - actual_floor_install_end)) / 86400.0
                    ELSE NULL
                END AS floor_post_work_duration
            FROM
                FloorPhaseActuals
        )
        SELECT
            AVG(floor_pre_work_duration) AS avg_floor_pre_work_days,
            AVG(floor_install_duration) AS avg_floor_install_days,
            AVG(floor_post_work_duration) AS avg_floor_post_work_days
        FROM
            FloorPhaseDurations;
    """
    with connection.cursor() as cursor:
        cursor.execute(floor_sql_query)
        result = cursor.fetchone()
        if result:
            avg_floor_times['pre_work'] = round(result[0], 0) if result[0] is not None else 0
            avg_floor_times['install'] = round(result[1], 0) if result[1] is not None else 0
            avg_floor_times['post_work'] = round(result[2], 0) if result[2] is not None else 0
            avg_floor_times['total'] = sum(filter(None, [avg_floor_times['pre_work'], avg_floor_times['install'], avg_floor_times['post_work']]))
            avg_floor_times['total'] = round(avg_floor_times['total'],0)

    return {
        'room_efficiency': {
            'average_time': avg_room_times,
            'expected_time': EXPECTED_ROOM_TIMES
        },
        'floor_efficiency': {
            'average_time': avg_floor_times,
            'expected_time': EXPECTED_FLOOR_TIMES
        }
    }

def _prepare_overall_project_time_data():
    """
    Calculates overall average room completion times for the project.
    Returns a dictionary formatted for the 'Overall Project Time' display.
    """
    data = {}
    avg_times = {'pre_work': 0, 'install': 0, 'post_work': 0, 'total': 0}

    # Reusing the same SQL logic for average room times
    room_sql_query = """
        SELECT
            AVG(CASE
                WHEN i.prework_check_on IS NOT NULL AND i.day_install_began IS NOT NULL AND i.prework_check_on >= i.day_install_began
                THEN EXTRACT(EPOCH FROM (i.prework_check_on - i.day_install_began)) / 86400.0
                ELSE NULL
            END) AS avg_room_pre_work_duration,
            AVG(CASE
                WHEN i.day_install_complete IS NOT NULL AND i.prework_check_on IS NOT NULL AND i.day_install_complete >= i.prework_check_on
                THEN EXTRACT(EPOCH FROM (i.day_install_complete - i.prework_check_on)) / 86400.0
                ELSE NULL
            END) AS avg_room_install_duration,
            AVG(CASE
                WHEN i.post_work_check_on IS NOT NULL AND i.day_install_complete IS NOT NULL AND i.post_work_check_on >= i.day_install_complete
                THEN EXTRACT(EPOCH FROM (i.post_work_check_on - i.day_install_complete)) / 86400.0
                ELSE NULL
            END) AS avg_room_post_work_duration
        FROM
            install i;
    """
    with connection.cursor() as cursor:
        cursor.execute(room_sql_query)
        result = cursor.fetchone()
        if result:
            avg_times['pre_work'] = round(result[0], 0) if result[0] is not None else 0
            avg_times['install'] = round(result[1], 0) if result[1] is not None else 0
            avg_times['post_work'] = round(result[2], 0) if result[2] is not None else 0
            avg_times['total'] = sum(filter(None, [avg_times['pre_work'], avg_times['install'], avg_times['post_work']]))
            avg_times['total'] = round(avg_times['total'],0)

    phases = ['pre_work', 'install', 'post_work', 'total']
    for phase in phases:
        avg = avg_times[phase]
        expected = EXPECTED_ROOM_TIMES[phase]
        data[phase] = {
            'avg': avg,
            'expected': expected,
            'is_delayed': avg > expected
        }
    return data

@login_required
def dashboard(request):
	try:
		floor_progress_list, total_rooms, completed_rooms, floor_summary = _prepare_floor_progress_data()
		pie_chart_data = _prepare_pie_chart_data(total_rooms, completed_rooms)
		efficiency_data = _prepare_efficiency_data()
		overall_project_time_data = _prepare_overall_project_time_data()
		
		# print("pie_chart_data :::: ",pie_chart_data)
		# print("Floor Summary::::", floor_summary)
		# print("Efficiency Data::::", efficiency_data)
		# print("Overall Project Time Data::::", overall_project_time_data)
		context = {
			'floor_progress_data': floor_progress_list,
			'pie_chart_data': pie_chart_data,
			'floor_status_summary': floor_summary,
			'efficiency_data': efficiency_data,
			'overall_project_time': overall_project_time_data,
			'page_name': 'Dashboard'
		}

		return render(
			request, "dashboard.html", context
		)
	except Exception as e:
		print(f"Error in dashboard view: {e}") 
		return redirect("admin/login")

@login_required
@user_passes_test(is_staff_user)
def admin_issue_create(request):
    if request.method == 'POST':
        form = IssueForm(request.POST, request.FILES)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.created_by = request.user  # or assign an admin user object
            issue.save()
            form.save_m2m()
            messages.success(request, f"Issue #{issue.id} created successfully.")
            return redirect('admin_dashboard:admin_issue_detail', issue_id=issue.id)
    else:
        form = IssueForm()
    return render(request, 'issues/issue_form.html', {'form': form, 'is_admin': True})


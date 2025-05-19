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
from django.db.models import Min, Max


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
@user_passes_test(is_staff_user)
def admin_issue_list(request):
	issues = Issue.objects.all().order_by('-created_at').select_related('created_by', 'assignee')

	# Filtering
	status = request.GET.get('status')
	issue_type = request.GET.get('type')
	created_by = request.GET.get('created_by')
	assignee = request.GET.get('assignee')
	q = request.GET.get('q')

	if q:
		issues = issues.filter(title__icontains=q)
	if status:
		issues = issues.filter(status=status)
	if issue_type:
		issues = issues.filter(type=issue_type)
	if created_by:
		issues = issues.filter(created_by__id=created_by)
	if assignee:
		issues = issues.filter(assignee__id=assignee)

	paginator = Paginator(issues, 25)
	page_number = request.GET.get('page')
	try:
		issues_page = paginator.page(page_number)
	except PageNotAnInteger:
		issues_page = paginator.page(1)
	except EmptyPage:
		issues_page = paginator.page(paginator.num_pages)

	# For filter dropdowns
	all_users = InvitedUser.objects.all()
	all_statuses = Issue._meta.get_field('status').choices
	all_types = Issue._meta.get_field('type').choices

	context = {
		'issues_page': issues_page,
		'all_users': all_users,
		'all_statuses': all_statuses,
		'all_types': all_types,
		'selected_status': status,
		'selected_type': issue_type,
		'selected_created_by': created_by,
		'selected_assignee': assignee,
		'search_query': q,
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
                WHEN i.prework_check_on IS NOT NULL AND s.floor_closes IS NOT NULL AND i.prework_check_on >= s.floor_closes
                THEN EXTRACT(EPOCH FROM (i.prework_check_on - s.floor_closes)) / 86400.0
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

        FROM install i
        JOIN room_data r ON r.room = i.room
        JOIN schedule s ON s.floor = r.floor;
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
                s.floor_closes AS actual_floor_pre_work_start,
                MAX(i.prework_check_on) AS actual_floor_pre_work_end,
                MAX(i.day_install_complete) AS actual_floor_install_end,
                MAX(i.post_work_check_on) AS actual_floor_post_work_end
            FROM
                install i
            JOIN
                room_data rd ON i.room = rd.room
            JOIN
                schedule s ON rd.floor = s.floor
            WHERE 
                rd.floor IS NOT NULL
            GROUP BY
                rd.floor, s.floor_closes
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
                WHEN i.prework_check_on IS NOT NULL AND s.floor_closes IS NOT NULL AND i.prework_check_on >= s.floor_closes
                THEN EXTRACT(EPOCH FROM (i.prework_check_on - s.floor_closes)) / 86400.0
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

        FROM install i
        JOIN room_data r ON r.room = i.room
        JOIN schedule s ON s.floor = r.floor;

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

def _calculate_date_details(schedule_date, actual_date, is_start_date_field=True):
    """
    Calculates difference, status, and CSS class for a pair of schedule/actual dates.
    Difference is schedule_date - actual_date.
    """
    details = {
        'schedule': schedule_date,
        'actual': actual_date,
        'difference': None,
        'status': '',
        'css_class': 'status-neutral'  # Default, e.g., for N/A values
    }

    if actual_date and schedule_date:
        try:
            # Ensure both are datetime.date objects if they are datetime.datetime
            if hasattr(schedule_date, 'date'):
                schedule_date = schedule_date.date()
            if hasattr(actual_date, 'date'):
                actual_date = actual_date.date()
            difference_days = (schedule_date - actual_date).days
        except TypeError: # Handle cases where one is date and other is datetime or other type issues
             difference_days = (schedule_date - actual_date).days if hasattr(schedule_date, 'date') and hasattr(actual_date, 'date') else None


        details['difference'] = difference_days
        if difference_days is not None:
            if is_start_date_field:
                if difference_days >= 0: # actual_date <= schedule_start_date (on time or early)
                    details['status'] = 'STARTED'
                    details['css_class'] = 'status-ok'
                else: # actual_date > schedule_start_date (delay)
                    details['status'] = 'DELAY'
                    details['css_class'] = 'status-delay'
            else: # End date field
                if difference_days >= 0: # actual_end_date <= schedule_end_date (on time or early)
                    details['status'] = 'OK'
                    details['css_class'] = 'status-ok'
                else: # actual_end_date > schedule_end_date (delay)
                    details['status'] = 'DELAY'
                    details['css_class'] = 'status-delay'
        else: # difference_days is None, implies a type issue before
            details['status'] = 'DATE ERROR'

    elif schedule_date: # Actual date is None, but schedule exists
        if is_start_date_field:
            details['status'] = 'NOT STARTED'
        else:
            details['status'] = 'NOT ENDED'
    else: # Schedule date is None (and actual might be None or present)
        details['status'] = 'N/A'
        if actual_date and not is_start_date_field : # If actual end date exists but no schedule end
             details['status'] = 'ENDED (NO SCHEDULE)'
        elif actual_date and is_start_date_field : # If actual start date exists but no schedule start
             details['status'] = 'STARTED (NO SCHEDULE)'


    return details

def _prepare_room_detail_report_context(request, room_number_query):
    """
    Prepares the context data for the Detail Report by Room section using direct SQL.
    Fetches room, schedule, and install data, calculates phase details,
    and handles messages for errors or warnings.
    """
    report_context = {
        'room_report_data': None,
        'queried_room_data': None, # For {{ queried_room_data.floor.floor_number }}
    }

    if not room_number_query:
        return report_context

    sql = """
        SELECT
            rd.room AS queried_room_value,
            rd.floor AS queried_floor_number,
            s.floor_closes AS s_prework_start,
            s.install_starts AS s_prework_end_or_install_start, -- Corrected from install_start
            s.install_ends AS s_install_end_or_postwork_start,   -- Corrected from install_end
            s.floor_completed AS s_postwork_end,             -- Corrected from floor_complete
            NULL AS a_prework_start,                          -- day_prework_began does not exist in Installation model
            i.prework_check_on AS a_prework_end,
            i.day_install_began AS a_install_start,
            i.day_install_complete AS a_install_end_or_postwork_start,
            i.post_work_check_on AS a_postwork_end
        FROM
            room_data rd
        LEFT JOIN
            schedule s ON s.floor = rd.floor
        LEFT JOIN
            install i ON i.room = rd.room
        WHERE
            rd.room = %s;
    """

    try:
        # Initialize all date variables to None to prevent NameError if data fetching fails partially
        s_prework_start, s_prework_end, a_prework_start, a_prework_end = None, None, None, None
        s_install_start, s_install_end, a_install_start, a_install_end = None, None, None, None
        s_postwork_start, s_postwork_end, a_postwork_start, a_postwork_end = None, None, None, None
        s_overall_start, s_overall_end, a_overall_start, a_overall_end = None, None, None, None

        with connection.cursor() as cursor:
            cursor.execute(sql, [room_number_query])
            result_row = _dictfetchall(cursor) # _dictfetchall returns a list

        if not result_row:
            messages.error(request, f"Room number {room_number_query} not found or no associated data.")
            return report_context
        
        data = result_row[0] # We expect only one row for a unique room number

        # Populate queried_room_data for template {{ queried_room_data.floor.floor_number }}
        report_context['queried_room_data'] = {
            'floor': {'floor_number': data.get('queried_floor_number')}
        }

        room_report_data = {}

        # Extract dates from the SQL result, defaulting to None if key missing (though LEFT JOIN means key exists, value can be NULL)
        s_prework_start = data.get('s_prework_start')
        s_prework_end = data.get('s_prework_end_or_install_start')
        a_prework_end = data.get('a_prework_end')
        room_report_data['prework'] = {
            'start': _calculate_date_details(s_prework_start, a_prework_start, is_start_date_field=True),
            'end': _calculate_date_details(s_prework_end, a_prework_end, is_start_date_field=False),
        }

        s_install_start = data.get('s_prework_end_or_install_start') # Scheduled install starts when prework ends
        s_install_end = data.get('s_install_end_or_postwork_start')
        a_install_start = data.get('a_install_start')
        a_install_end = data.get('a_install_end_or_postwork_start') # Actual install ends
        room_report_data['install'] = {
            'start': _calculate_date_details(s_install_start, a_install_start, is_start_date_field=True),
            'end': _calculate_date_details(s_install_end, a_install_end, is_start_date_field=False),
        }

        s_postwork_start = data.get('s_install_end_or_postwork_start') # Scheduled post-work starts when install ends
        s_postwork_end = data.get('s_postwork_end')
        a_postwork_start = data.get('a_install_end_or_postwork_start') # Actual post-work starts when install is completed
        a_postwork_end = data.get('a_postwork_end')
        room_report_data['postwork'] = {
            'start': _calculate_date_details(s_postwork_start, a_postwork_start, is_start_date_field=True),
            'end': _calculate_date_details(s_postwork_end, a_postwork_end, is_start_date_field=False),
        }
        
        # OVERALL Calculation (uses the individual phase dates extracted above)
        all_schedule_starts = [d for d in [s_prework_start, s_install_start, s_postwork_start] if d]
        all_schedule_ends = [d for d in [s_prework_end, s_install_end, s_postwork_end] if d]
        all_actual_starts = [d for d in [a_prework_start, a_install_start, a_postwork_start] if d]
        all_actual_ends = [d for d in [a_prework_end, a_install_end, a_postwork_end] if d]

        s_overall_start = min(all_schedule_starts) if all_schedule_starts else None
        s_overall_end = max(all_schedule_ends) if all_schedule_ends else None
        a_overall_start = min(all_actual_starts) if all_actual_starts else None
        a_overall_end = max(all_actual_ends) if all_actual_ends else None
        
        room_report_data['overall'] = {
            'start': _calculate_date_details(s_overall_start, a_overall_start, is_start_date_field=True),
            'end': _calculate_date_details(s_overall_end, a_overall_end, is_start_date_field=False),
        }
        report_context['room_report_data'] = room_report_data

    except Exception as e_sql_report:
        logger.error(f"SQL Error or data processing error in room detail report for {room_number_query}: {e_sql_report}")
        messages.error(request, f"An error occurred while generating the detailed report for room {room_number_query}.")
        # report_context already has None for data fields

    return report_context

@login_required
def dashboard(request):
    try:
        floor_progress_list, total_rooms, completed_rooms, floor_summary = _prepare_floor_progress_data()
        pie_chart_data = _prepare_pie_chart_data(total_rooms, completed_rooms)
        efficiency_data = _prepare_efficiency_data()
        overall_project_time_data = _prepare_overall_project_time_data()
        
        context = {
            'floor_progress_data': floor_progress_list,
            'pie_chart_data': pie_chart_data,
            'floor_status_summary': floor_summary,
            'efficiency_data': efficiency_data,
            'overall_project_time': overall_project_time_data,
            'page_name': 'Dashboard',
            'room_report_data': None, 
            'queried_room_data': None,
            'room_number_query': '' 
        }

        room_number_query = request.GET.get('room_number', '').strip()
        context['room_number_query'] = room_number_query

        if room_number_query:
            room_report_specific_context = _prepare_room_detail_report_context(request, room_number_query)
            print(f"Room report specific context: {room_report_specific_context}")
            context.update(room_report_specific_context)

        return render(
            request, "dashboard.html", context
        )
    except Exception as e:
        logger.error(f"Generic error in dashboard view: {e}")
        messages.error(request, "An error occurred while loading the dashboard.")
        return redirect("admin_dashboard:login") 

@login_required
@user_passes_test(is_staff_user)
def admin_issue_create(request):
    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data.setlist('related_rooms', request.POST.getlist('related_rooms'))
        post_data.setlist('related_inventory_items', request.POST.getlist('related_inventory_items'))
        form = IssueForm(post_data, request.FILES)
        if form.is_valid():
            issue = form.save(commit=False)
            user = get_object_or_404(InvitedUser, id=request.user.id)
            issue.created_by = user
            issue.save()
            form.save_m2m()
            messages.success(request, f"Issue #{issue.id} created successfully.")
            return redirect('admin_dashboard:admin_issue_detail', issue_id=issue.id)
    else:
        form = IssueForm()
    return render(
        request,
        'admin_dashboard/issues/admin_issue_form.html',
        {
            'form': form,
            'is_admin': True,
            'form_action': reverse('admin_dashboard:admin_issue_create')
        }
    )


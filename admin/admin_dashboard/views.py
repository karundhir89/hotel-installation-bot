from django.shortcuts import render,HttpResponseRedirect, redirect, get_object_or_404
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from .models import *
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse # Though reverse might not be strictly needed if using namespaced redirects
import uuid
from django.core.files.storage import default_storage
import json # For AJAX error responses if you re-add them later

# Assuming models and forms are in hotel_bot_app. Adjust if your structure is different.
# You might need to adjust the import path if admin_dashboard and hotel_bot_app are at different levels
# e.g., from ..hotel_bot_app.models import ... if they are sibling apps under 'admin/' directory
from hotel_bot_app.models import Issue, Comment, InvitedUser 
from hotel_bot_app.forms import IssueUpdateForm, CommentForm 

import logging
logger = logging.getLogger(__name__)

# Define a check for staff users (Django's concept of admin users)
def is_staff_user(user):
	return user.is_authenticated and user.is_staff # or user.is_superuser

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
def dashboard(request):
	try:
		return render(request,'dashboard.html')
	except Exception as e:
		print("error in dashboard :::::::::::",e)

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
	
	if request.method == 'POST':
		form = IssueUpdateForm(request.POST, instance=issue)
		if form.is_valid():
			form.save()
			messages.success(request, f"Issue #{issue.id} updated successfully.")
			return redirect('admin_dashboard:admin_issue_list') 
		else:
			messages.error(request, "Please correct the errors below.")
	else:
		form = IssueUpdateForm(instance=issue)
	
	context = {
		'form': form,
		'issue': issue,
	}
	return render(request, 'admin_dashboard/issues/admin_issue_form.html', context)

@login_required
@user_passes_test(is_staff_user)
def admin_issue_detail(request, issue_id):
	issue = get_object_or_404(Issue, id=issue_id)
	comments = issue.comments.all().select_related('content_type') 
	for comment in comments: 
		_ = comment.commenter 

	comment_form = CommentForm() 

	context = {
		'issue': issue,
		'comments': comments,
		'comment_form': comment_form,
		'user': request.user 
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
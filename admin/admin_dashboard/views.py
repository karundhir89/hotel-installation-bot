from django.shortcuts import render,HttpResponseRedirect
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from .models import *

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
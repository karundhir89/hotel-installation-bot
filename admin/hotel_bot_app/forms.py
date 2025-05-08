# from django import forms
# from django.core.exceptions import ValidationError
# from .models import Issue, Comment, InvitedUser

# # from django.forms.widgets import FileInput

# # class MultipleFileInput(FileInput):
# #     def __init__(self, attrs=None):
# #         super().__init__(attrs)

# #     def value_from_datadict(self, data, files, name):
# #         if hasattr(files, 'getlist'):
# #             return files.getlist(name)
# #         return files.get(name)

# # class IssueForm(forms.ModelForm):
# #     initial_comment = forms.CharField(widget=forms.Textarea, required=True)

# #     images = forms.FileField(
# #         widget=MultipleFileInput(attrs={'class': 'form-control'}),
# #         required=False
# #     )
# #     video = forms.FileField(required=False)

# #     class Meta:
# #         model = Issue
# #         fields = ['title', 'type', 'description']

# #     def clean_images(self):
# #         images = self.files.getlist('images')
# #         if len(images) > 4:
# #             raise ValidationError("You can upload up to 4 images.")
# #         for img in images:
# #             if not img.content_type.startswith('image/'):
# #                 raise ValidationError("Only image files are allowed.")
# #         return images

# #     def clean_video(self):
# #         video = self.cleaned_data.get('video')
# #         if video:
# #             if not video.content_type.startswith('video/'):
# #                 raise ValidationError("Only video files are allowed.")
# #             if video.size > 100 * 1024 * 1024:
# #                 raise ValidationError("Video file must be under 100MB.")
# #         return video
# from django import forms
# class MultipleFileInput(forms.ClearableFileInput):
#     allow_multiple_selected = True

#     def __init__(self, attrs=None):
#         if attrs is not None:
#             attrs = attrs.copy()
#         else:
#             attrs = {}
#         attrs.update({'multiple': 'multiple'})
#         super().__init__(attrs)

#     def value_from_datadict(self, data, files, name):
#         if name in files:
#             return files.getlist(name)
#         return []

# class IssueForm(forms.ModelForm):
#     initial_comment = forms.CharField(widget=forms.Textarea, required=True)
#     images = forms.FileField(
#         widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
#         required=False
#     )
#     video = forms.FileField(
#         widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
#         required=False
#     )

#     class Meta:
#         model = Issue
#         fields = ['title', 'type', 'description']

#     def clean_images(self):
#         images = self.cleaned_data.get('images', [])  # Default to empty list
#         if images:  # Only validate if files are provided
#             if len(images) > 4:
#                 raise ValidationError("You can upload up to 4 images.")
#             for img in images:
#                 if not img.content_type.startswith('image/'):
#                     raise ValidationError("Only image files are allowed.")
#         return images

#     def clean_video(self):
#         video = self.cleaned_data.get('video')
#         if video:
#             if not video.content_type.startswith('video/'):
#                 raise ValidationError("Only video files are allowed.")
#             if video.size > 100 * 1024 * 1024:
#                 raise ValidationError("Video file must be under 100MB.")
#         return video

# # ---- ADD THIS DEBUG PRINT ----
# print(f"DEBUG: forms.FileInput is: {forms.FileInput}")
# print(f"DEBUG: forms.FileInput type is: {type(forms.FileInput)}")
# # ------------------------------

# class CommentForm(forms.ModelForm):
#     images = forms.FileField(
#         widget=forms.FileInput(attrs={'multiple': True, 'class': 'form-control'}), 
#         required=False,
#         label="Attach Images (Max 4)"
#     )
#     video = forms.FileField(
#         widget=forms.FileInput(attrs={'class': 'form-control'}),
#         required=False,
#         label="Attach Video (Max 100MB)"
#     )

#     class Meta:
#         model = Comment
#         fields = ['text_content', 'images', 'video']
#         widgets = {
#             'text_content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add your comment...', 'class': 'form-control'})
#         }
#         labels = {
#             'text_content': 'Your Comment'
#         }

#     def clean_images(self):
#         images = self.files.getlist('images')
#         if len(images) > 4:
#             raise ValidationError("You can upload a maximum of 4 images.")
#         for image in images:
#             if not image.content_type.startswith('image/'):
#                 raise ValidationError(f"File '{image.name}' is not a valid image.")
#         return images

#     def clean_video(self):
#         video = self.cleaned_data.get('video')
#         if video:
#             if not video.content_type.startswith('video/'):
#                 raise ValidationError("The uploaded file is not a valid video.")
#             if video.size > 100 * 1024 * 1024: # 100MB
#                 raise ValidationError("Video file size cannot exceed 100MB.")
#         return video

#     def clean(self):
#         cleaned_data = super().clean()
#         text_content = cleaned_data.get("text_content")
#         images = self.files.getlist('images') 
#         video = cleaned_data.get("video")

#         if not text_content and not images and not video:
#             raise ValidationError("A comment must contain text or at least one media file.")
#         return cleaned_data

# # Optional form for Admins to edit issue details like assignee, status, etc.
# class IssueUpdateForm(forms.ModelForm):
#      assignee = forms.ModelChoiceField(
#          queryset=InvitedUser.objects.all(), # Use InvitedUser here
#          required=False,
#          widget=forms.Select(attrs={'class': 'form-select'})
#      )
#      observers = forms.ModelMultipleChoiceField(
#          queryset=InvitedUser.objects.all(), # Use InvitedUser here
#          required=False,
#          widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'})
#      )

#      class Meta:
#          model = Issue
#          fields = ['title', 'description', 'status', 'type', 'is_for_hotel_admin', 'assignee', 'observers']
#          widgets = {
#              'description': forms.Textarea(attrs={'rows': 3}),
#              'status': forms.Select(attrs={'class': 'form-select'}),
#              'type': forms.Select(attrs={'class': 'form-select'}),
#              'is_for_hotel_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
#          } 

from django import forms
from django.core.exceptions import ValidationError
from .models import Issue, Comment, InvitedUser

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is not None:
            attrs = attrs.copy()
        else:
            attrs = {}
        attrs.update({'multiple': 'multiple'})
        super().__init__(attrs)

    def value_from_datadict(self, data, files, name):
        if name in files:
            return files.getlist(name)
        return []

class IssueForm(forms.ModelForm):
    initial_comment = forms.CharField(widget=forms.Textarea, required=True)
    images = forms.FileField(
        widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        required=False
    )
    video = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
        required=False
    )

    class Meta:
        model = Issue
        fields = ['title', 'type', 'description']

    def clean_images(self):
        images = self.cleaned_data.get('images', [])  # Default to empty list
        if images:  # Only validate if files are provided
            if len(images) > 4:
                raise ValidationError("You can upload up to 4 images.")
            for img in images:
                if not img.content_type.startswith('image/'):
                    raise ValidationError("Only image files are allowed.")
        return images

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if not video.content_type.startswith('video/'):
                raise ValidationError("Only video files are allowed.")
            if video.size > 100 * 1024 * 1024:
                raise ValidationError("Video file must be under 100MB.")
        return video

class CommentForm(forms.ModelForm):
    images = forms.FileField(
        widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        required=False,
        label="Attach Images (Max 4)"
    )
    video = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
        required=False,
        label="Attach Video (Max 100MB)"
    )

    class Meta:
        model = Comment
        fields = ['text_content', 'images', 'video']
        widgets = {
            'text_content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add your comment...', 'class': 'form-control'})
        }
        labels = {
            'text_content': 'Your Comment'
        }

    def clean_images(self):
        images = self.cleaned_data.get('images', [])  # Default to empty list
        if images:  # Only validate if files are provided
            if len(images) > 4:
                raise ValidationError("You can upload a maximum of 4 images.")
            for image in images:
                if not image.content_type.startswith('image/'):
                    raise ValidationError(f"File '{image.name}' is not a valid image.")
        return images

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if not video.content_type.startswith('video/'):
                raise ValidationError("The uploaded file is not a valid video.")
            if video.size > 100 * 1024 * 1024:  # 100MB
                raise ValidationError("Video file size cannot exceed 100MB.")
        return video

    def clean(self):
        cleaned_data = super().clean()
        text_content = cleaned_data.get("text_content")
        images = cleaned_data.get("images", [])
        video = cleaned_data.get("video")

        if not text_content and not images and not video:
            raise ValidationError("A comment must contain text or at least one media file.")
        return cleaned_data

class IssueUpdateForm(forms.ModelForm):
    assignee = forms.ModelChoiceField(
        queryset=InvitedUser.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    observers = forms.ModelMultipleChoiceField(
        queryset=InvitedUser.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'})
    )

    class Meta:
        model = Issue
        fields = ['title', 'description', 'status', 'type', 'is_for_hotel_admin', 'assignee', 'observers']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'is_for_hotel_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.created_by:
            # Ensure the creator is always included in the initial observers
            self.initial['observers'] = self.instance.observers.all() | InvitedUser.objects.filter(pk=self.instance.created_by.pk)

    def clean_observers(self):
        observers = self.cleaned_data.get('observers')
        if observers:
            # Ensure uniqueness in the cleaned data
            unique_observers = list(dict.fromkeys(observers))
            return unique_observers
        return observers
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
from .models import Issue, Comment, InvitedUser, RoomData, Inventory

from django.forms.widgets import FileInput
class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Handle multiple files from files.getlist
        if not data and initial:
            return initial
        if not data:
            if self.required:
                raise ValidationError(self.error_messages['required'], code='required')
            return []
        if not isinstance(data, list):
            data = [data]
        return data  # Return
class MultipleFileInput(forms.FileInput):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        if attrs is None:
            attrs = {}
        attrs['multiple'] = True

    def value_from_datadict(self, data, files, name):
        return files.getlist(name)  # Always return a list

    def value_omitted_from_data(self, data, files, name):
        return not files.getlist(name)  # True if no files
class IssueForm(forms.ModelForm):
    # initial_comment = forms.CharField(widget=forms.Textarea, required=True)
    images = MultipleFileField(
        widget=MultipleFileInput(attrs={'class': 'form-control d-none', 'accept': 'image/*'}),
        required=False,
        label="Attach Images (Max 4)"
    )
    video = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control d-none', 'accept': 'video/*'}),
        required=False
    )
    related_rooms = forms.ModelMultipleChoiceField(
        queryset=RoomData.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2-multiple'}),
        required=False,
    )
    related_inventory_items = forms.ModelMultipleChoiceField(
        queryset=Inventory.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2-multiple'}),
        required=False,
    )

    class Meta:
        model = Issue
        fields = ['title', 'type', 'description', 'images', 'video', 'related_rooms', 'related_inventory_items']
        widgets = {
            'type': forms.RadioSelect
        }
        # Note: initial_comment, images, video are not model fields but handled in the view. Here they are form fields.
        # related_rooms and related_inventory_items are actual model fields.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure all fields that might be dynamically shown/hidden are present
        if 'related_rooms' not in self.fields or not isinstance(self.fields['related_rooms'].widget, forms.SelectMultiple):
            self.fields['related_rooms'] = forms.ModelMultipleChoiceField(
                queryset=RoomData.objects.all(),
                widget=forms.SelectMultiple(attrs={'class': 'form-check select2-multiple'}),
                required=False,
                label="Related Rooms (if type is Room)"
            )
        if 'related_inventory_items' not in self.fields or not isinstance(self.fields['related_inventory_items'].widget, forms.SelectMultiple):
            self.fields['related_inventory_items'] = forms.ModelMultipleChoiceField(
                queryset=Inventory.objects.all(),
                widget=forms.SelectMultiple(attrs={'class': 'form-check select2-multiple'}),
                required=False,
                label="Related Floor Items (if type is Floor)"
            )

        self.fields['type'].choices = [
            ('ROOM', 'Room Issue'),
            ('FLOOR', 'Floor Issue'),
        ]
        
        # Set default to ROOM if not already set
        if not self.initial.get('type'):
            self.initial['type'] = 'ROOM'
    def clean_images(self):
        images = self.cleaned_data.get('images', [])
        if images:
            if len(images) > 4:
                raise ValidationError("You can upload a maximum of 4 images.")
            for image in images:
                if not image.content_type.startswith('image/'):
                    raise ValidationError(f"File '{image.name}' is not a valid image.")
                if image.size > 4 * 1024 * 1024:
                    raise ValidationError(f"Image '{image.name}' exceeds 4MB limit.")
        return images

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if not video.content_type.startswith('video/'):
                raise ValidationError("Only video files are allowed.")
            if video.size > 100 * 1024 * 1024:
                raise ValidationError("Video file must be under 100MB.")
        return video
    
    def clean(self):
        cleaned_data = super().clean()
        issue_type = cleaned_data.get("type")
        related_rooms = cleaned_data.get("related_rooms")
        related_inventory_items = cleaned_data.get("related_inventory_items")

        if issue_type == "ROOM" and not related_rooms:
            self.add_error('related_rooms', "Please select at least one room for issues of type 'Room'.")
        elif issue_type == "FLOOR" and not related_inventory_items:
            self.add_error('related_inventory_items', "Please select at least one floor item for issues of type 'Floor'.")

        # Clear irrelevant fields
        if issue_type != "ROOM":
            cleaned_data['related_rooms'] = RoomData.objects.none()
        if issue_type != "FLOOR":
            cleaned_data['related_inventory_items'] = Inventory.objects.none()

        return cleaned_data

class CommentForm(forms.ModelForm):
    text_content = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 1, 'placeholder': 'Add your comment...', 'class': 'form-control'}),
        label='Your Comment',
        required=False
    )
    images = MultipleFileField(
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

    def clean_images(self):
        images = self.cleaned_data.get('images', [])
        print(f"Images in clean_images: {images}")  # Debug
        if images:
            if len(images) > 4:
                raise ValidationError("You can upload a maximum of 4 images.")
            for image in images:
                if not image.content_type.startswith('image/'):
                    raise ValidationError(f"File '{image.name}' is not a valid image.")
                if image.size > 4 * 1024 * 1024:
                    raise ValidationError(f"Image '{image.name}' exceeds 4MB limit.")
        return images

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if not video.content_type.startswith('video/'):
                raise ValidationError("The uploaded file is not a valid video.")
            if video.size > 100 * 1024 * 1024:
                raise ValidationError("Video file size cannot exceed 100MB.")
        return video

    def clean(self):
        cleaned_data = super().clean()
        text_content = cleaned_data.get('text_content')
        images = cleaned_data.get('images', [])  # Use cleaned_data
        video = cleaned_data.get('video')
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
            'description': forms.Textarea(attrs={'rows': 1}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'is_for_hotel_admin': forms.Select(choices=[
                (False, 'Hidden from Hotel Admin'),
                (True, 'Visible to Hotel Admin')
                ], attrs={'class': 'form-select'}),

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

    # Update type choices for edit form
    def clean_type(self):
        type = self.cleaned_data.get('type')
        if type not in ['ROOM', 'FLOOR']:
            raise ValidationError("Invalid type selected.")
        return type
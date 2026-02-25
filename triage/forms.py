from allauth.account.forms import SignupForm
from django import forms
from .models import Patient
import re
from django.core.exceptions import ValidationError


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"})
    )
    gender = forms.ChoiceField(
        choices=Patient.GENDER_CHOICES
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields["first_name"].widget.attrs.update({
            "placeholder": "First name",
        })

        self.fields["last_name"].widget.attrs.update({
            "placeholder": "Last name",
        })
        
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-mesh-500 transition duration-200"
            })
    def clean_first_name(self):
        first_name = self.cleaned_data.get("first_name", "").strip()

        if len(first_name) < 2:
            raise ValidationError("First name must be at least 2 characters.")

        if not re.match(r"^[A-Za-z\s\-']+$", first_name):
            raise ValidationError("First name can only contain letters.")

        return first_name


    def clean_last_name(self):
        last_name = self.cleaned_data.get("last_name", "").strip()

        if len(last_name) < 2:
            raise ValidationError("Last name must be at least 2 characters.")

        if not re.match(r"^[A-Za-z\s\-']+$", last_name):
            raise ValidationError("Last name can only contain letters.")

        return last_name

    def save(self, request):
        user = super().save(request)

        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()

        Patient.objects.create(
            user=user,
            date_of_birth=self.cleaned_data["date_of_birth"],
            gender=self.cleaned_data["gender"],
        )

        return user

from django.shortcuts import render
from django.http import HttpResponse

def dashboard(request):
    return render(request, 'triage/dashboard.html')

def triage_updates(request):
    # Placeholder for HTMX updates
    return HttpResponse("<!-- HTMX partial content -->")

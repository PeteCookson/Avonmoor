from django.shortcuts import render

# This will be the landing page view
def index(request):
    return render(request, 'about/index.html')
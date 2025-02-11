from django.shortcuts import render

# This will be the landing page view
def garden(request):
    return render(request, 'garden/garden.html')
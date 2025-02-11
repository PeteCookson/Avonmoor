from django.shortcuts import render

# This will be the landing page view
def property(request):
    return render(request, 'property/property.html')

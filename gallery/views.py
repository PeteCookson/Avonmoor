from django.shortcuts import render

# This will be the landing page view
def gallery(request):
    return render(request, 'gallery/gallery.html')
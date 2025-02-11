from django.shortcuts import render

# This will be the landing page view
def blog(request):
    return render(request, 'blog/blog.html')
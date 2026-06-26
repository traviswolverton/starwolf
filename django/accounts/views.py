from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import redirect, render


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.GET.get("next", "/"))

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.POST.get("next", "/"))
        error = "Invalid username or password."

    return render(request, "accounts/login.html", {
        "next": request.GET.get("next", "/"),
        "error": error,
    })


def logout_view(request):
    logout(request)
    return redirect("/")

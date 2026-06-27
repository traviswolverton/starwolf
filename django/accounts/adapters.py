from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import render


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Block email/password registration; social signup handled separately
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        # Always allow new accounts via Google, GitHub, Discord
        return True

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        # Return 200 so the proxy doesn't intercept the error page as a 401
        return render(request, "socialaccount/authentication_error.html", status=200)

    def populate_username(self, request, user):
        user.username = user.email

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.username = user.email
        if commit:
            user.save()
        return user

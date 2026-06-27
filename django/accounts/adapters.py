from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Social auth only — block email/password registration
        return False

    def populate_username(self, request, user):
        user.username = user.email

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.username = user.email
        if commit:
            user.save()
        return user

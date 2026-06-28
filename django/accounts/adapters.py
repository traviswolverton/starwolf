from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return True

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not user.username:
            user.username = user.email
            user.save(update_fields=["username"])
        return user

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Social auth error provider=%s error=%r exception=%r extra=%r", provider, error, exception, extra_context)

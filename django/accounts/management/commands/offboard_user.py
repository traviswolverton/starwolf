from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Deactivate a user by email (soft-delete — preserves preferences for re-activation)"

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email address of the user to deactivate")
        parser.add_argument(
            "--reactivate",
            action="store_true",
            help="Re-activate a previously deactivated user instead",
        )

    def handle(self, *args, **options):
        email = options["email"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email: {email}")

        if options["reactivate"]:
            user.is_active = True
            user.save(update_fields=["is_active"])
            self.stdout.write(self.style.SUCCESS(f"Re-activated {email}"))
        else:
            user.is_active = False
            user.save(update_fields=["is_active"])
            self.stdout.write(self.style.SUCCESS(f"Deactivated {email} (preferences preserved)"))
